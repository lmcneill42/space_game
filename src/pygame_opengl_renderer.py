import pygame
import OpenGL
import OpenGL.GL as GL
import math
import os
import os.path

from pymunk import Vec2d

from .renderer import *

class ShaderProgram(object):
    """ Manages an OpenGL shader program.

    Note that the program will currently never be deleted. My thinking
    is that there won't be many shaders, and so we will leave them to be
    cleaned up when the program terminates. """

    def __init__(self, filename_type_pairs, attribs, uniforms):
        """ Constructor - create and initialise a shader program.

        'filename_type_pairs' is a list of (filename, enum) tuples
        that specify the shader source to load and what type of
        shaders they are.

        'attribs' is a list of vertex attributes used in the shader
        program.

        'uniforms' is a list of uniform state used in the shader
        program.

        These will correspond to variables declared in the shader
        source.
        """

        # Note: see the following, which was referenced in the PyOpenGL
        # documentation:
        #       https://bitbucket.org/rndblnch/opengl-programmable/src/tip/10-g
        #       l3.2core.py?fileviewer=file-view-default

        # Create the program object.
        self.__shader_program = GL.glCreateProgram()

        # Assign locations to vertex attributes. We'll bind them in the program later...
        self.__attrib_locations = dict((k, v) for (v, k) in enumerate(attribs))

        # Uniform locations will be determined by OpenGL, we'll get them later.
        self.__uniform_locations = {}

        # Compile all of the source files and attach the resulting
        # shader objects to our shader program.
        for (filename, shader_type) in filename_type_pairs:
            shader = GL.glCreateShader(shader_type)
            GL.glShaderSource(shader, open(filename, 'r').read())
            GL.glCompileShader(shader)
            if GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) != GL.GL_TRUE:
                raise Exception(GL.glGetShaderInfoLog(shader))
            GL.glAttachShader(self.__shader_program, shader)

        # Now we can bind all of the vertex attributes to their
        # assigned locations.
        for attrib in attribs:
            GL.glBindAttribLocation(self.__shader_program,
                                    self.__attrib_locations[attrib],
                                    attrib)

        # Now link the program.
        GL.glLinkProgram(self.__shader_program)
        if GL.glGetProgramiv(self.__shader_program, GL.GL_LINK_STATUS) != GL.GL_TRUE:
            raise Exception(GL.glGetProgramInfoLog(self.__shader_program))

        # Retrieve the uniform locations and remember them.
        for uniform in uniforms:
            self.__uniform_locations[uniform] = GL.glGetUniformLocation(self.__shader_program, uniform)

    def begin(self):
        """ Render using the shader program. """
        GL.glUseProgram(self.__shader_program)

    def end(self):
        """ Render using the fixed function pipeline. """
        GL.glUseProgram(0)

class Texture(object):
    """ An OpenGL texture. """

    @classmethod
    def from_file(klass, filename):
        """ Create a texture from a file. """
        surface = pygame.image.load(filename).convert_alpha()
        return Texture(surface)

    @classmethod
    def from_surface(klass, surface):
        """ Create a texture from a surface. """
        return Texture(surface)

    def __init__(self, surface):
        """ Constructor. """
        data = pygame.image.tostring(surface, "RGBA", 1)
        self.__width = surface.get_width()
        self.__height = surface.get_height()
        self.__texture = GL.glGenTextures(1)
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.__texture)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.get_width(), self.get_height(),
                        0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, data)
        GL.glDisable(GL.GL_TEXTURE_2D)

    def begin(self):
        """ Set OpenGL state. """
        assert self.__texture is not None
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.__texture)
        GL.glColor3f(1, 1, 1)

    def end(self):
        """ Unset the state. """
        assert self.__texture is not None
        GL.glDisable(GL.GL_TEXTURE_2D)

    def get_width(self):
        """ Get the texture width in pixels. """
        assert self.__texture is not None
        return self.__width

    def get_height(self):
        """ Get the texture height in pixels. """
        assert self.__texture is not None
        return self.__height

    def get_size(self):
        """ Get the texture size in pixels. """
        assert self.__texture is not None
        return (self.__width, self.__height)

    def delete(self):
        """ Free the texture. """
        if self.__texture is not None:
            GL.glDeleteTextures(self.__texture)
            self.__texture = None

    def __del__(self):
        """ Ensure the OpenGL texture gets deleted. """
        self.delete()

class TextureSequence(object):
    """ A sequence of textures. """

    # Note: this is not really a practical implementation, we have lots of
    # large frames per anim so that's lots of textures. It would be good to
    # use a texture atlas or array texture for the frames rather than a
    # texture per frame.

    def __init__(self, filenames):
        """ Constructor. """
        self.__textures = [Texture.from_file(f) for f in filenames]
        self.__bound_texture = None

    def begin(self, timer):
        """ Set the state. """
        assert self.__bound_texture is None
        idx = timer.pick_index(len(self.__textures))
        self.__bound_texture = self.__textures[idx]
        self.__bound_texture.begin()

    def end(self):
        """ Unset the state. """
        assert self.__bound_texture is not None
        self.__bound_texture.end()
        self.__bound_texture = None

    def get_width(self):
        """ The texture width. """
        return self.__textures[0].get_width()

    def get_height(self):
        """ The texture height. """
        return self.__textures[0].get_height()

    def get_frame(self, timer):
        """ Get a frame from a timer. """
        idx = timer.pick_index(len(self.__textures))
        return self.__textures[idx]

class TextureArray(object):
    """ A texture array for rendering many sprites without changing
    textures. """

    def __init__(self, files):

        # Read in each image file and determine the maximum extents,
        # remembering the extents of each one.
        self.__max_width = 0
        self.__max_height = 0
        self.__texture_dimensions = []
        images = []
        for filename in files:
            surf = pygame.image.load(filename)
            self.__max_width = max(self.__max_width, surf.get_width())
            self.__max_height = max(self.__max_height, surf.get_height())
            self.__texture_dimensions.append(surf.get_size())
            images.append(surf)

        # Allocate the texture array.
        self.__texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D_ARRAY, self.__texture)
        GL.glTexImage3D(
            GL.GL_TEXTURE_2D_ARRAY,
            0, #level
            GL.GL_RGBA8, # internal format
            self.__max_width,
            self.__max_height,
            len(images),
            0, #border
            GL.GL_RGBA, # format
            GL.GL_UNSIGNED_BYTE, # data type
            None # The data.
        )

        # Upload each image to the array.
        for (i, image) in enumerate(images):
            image_bytes = pygame.image.tostring(image, "RGBA", 1)
            GL.glTexSubImage3D(
                GL.GL_TEXTURE_2D_ARRAY,
                0, # Mipmap number
                0, # x offset
                0, # y offset
                i, # z offset
                image.get_width(),
                image.get_height(),
                1, # Depth
                GL.GL_RGBA, # format
                GL.GL_UNSIGNED_BYTE, # data type
                image_bytes # data
            )

    def begin(self):
        """ Begin rendering with the texture array. """
        GL.glBindTexture(GL.GL_TEXTURE_2D_ARRAY, self.__texture)

    def end(self):
        """ Stop rendering with the texture array. """
        pass

class PygameOpenGLRenderer(Renderer):
    """ A pygame software renderer. """

    def __init__(self):
        """ Constructor. """
        Renderer.__init__(self)
        self.__surface = None

    def initialise(self, screen_size, data_path):
        """ Initialise the pygame display. """
        self.__surface = pygame.display.set_mode(screen_size, pygame.DOUBLEBUF|pygame.OPENGL)
        self.__data_path = data_path
        GL.glViewport(0, 0, self.__surface.get_width(), self.__surface.get_height())
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, self.__surface.get_width(), self.__surface.get_height(), 0, 0, 1)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        print ("OpenGL version: %s" % GL.glGetString(GL.GL_VERSION))
        print ("OpenGL vendor: %s" % GL.glGetString(GL.GL_VENDOR))

        self.__anim_shader = ShaderProgram(
            ((os.path.join(self.__data_path, "shaders/anim/anim.v.glsl"), GL.GL_VERTEX_SHADER),
             (os.path.join(self.__data_path, "shaders/anim/anim.f.glsl"), GL.GL_FRAGMENT_SHADER)),
            ("vertex"), # Attributes
            () # Uniforms
        )

        self.__filenames = []
        self.__texture_array = None

    def post_preload(self):
        """ Initialise the texture array. """
        self.__texture_array = TextureArray(self.__filenames)

    def flip_buffers(self):
        """ Update the pygame display. """
        pygame.display.flip()

    def load_compatible_image(self, filename):
        """ Load a pygame image. """
        self.__filenames.append(filename)
        return Texture.from_file(filename)

    def load_compatible_anim_frames(self, filename_list):
        """ Load the frames of an animation into a format compatible
        with the renderer.  The implementation can return its own
        image representation; the client should treat it as an opaque
        object. """
        self.__filenames += filename_list
        return TextureSequence(filename_list)

    def load_compatible_font(self, filename, size):
        """ Load a pygame font. """
        return pygame.font.Font(filename, size)

    def compatible_image_from_text(self, text, font, colour):
        """ Create an image by rendering a text string. """
        return Texture.from_surface(font.render(text, True, colour))

    def screen_size(self):
        """ Get the display size. """
        return self.__surface.get_size()

    def screen_rect(self):
        """ Get the display size. """
        return self.__surface.get_rect()

    def render_RenderJobBackground(self, job):
        """ Render scrolling background. """
        (w, h) = self.screen_size()
        self.render_image(job.background_image, w, h, Vec2d(0, 0))

    def render_RenderJobRect(self, job):
        """ Render rectangle. """
        rect = job.rect
        tl = rect.topleft
        tr = rect.topright
        br = rect.bottomright
        bl = rect.bottomleft
        GL.glColor3f(*self.colour_int_to_float(job.colour))
        if job.width == 0:
            GL.glBegin(GL.GL_QUADS)
        else:
            GL.glLineWidth(job.width)
            GL.glBegin(GL.GL_LINE_LOOP)
        GL.glVertex2f(tl[0], tl[1])
        GL.glVertex2f(tr[0], tr[1])
        GL.glVertex2f(br[0], br[1])
        GL.glVertex2f(bl[0], bl[1])
        GL.glEnd()

    def render_RenderJobLine(self, job):
        """ Render a line. """
        GL.glLineWidth(job.width)
        GL.glColor3f(*self.colour_int_to_float(job.colour))
        GL.glBegin(GL.GL_LINES)
        GL.glVertex2f(job.p0[0], job.p0[1])
        GL.glVertex2f(job.p1[0], job.p1[1])
        GL.glEnd()

    def render_RenderJobLines(self, job):
        """ Render a polyline. """
        GL.glLineWidth(job.width)
        GL.glColor3f(*self.colour_int_to_float(job.colour))
        GL.glBegin(GL.GL_LINE_STRIP)
        for point in job.points:
            GL.glVertex2f(point[0], point[1])
        GL.glEnd()

    def render_RenderJobPolygon(self, job):
        """ Render a polygon. """
        GL.glColor3f(*self.colour_int_to_float(job.colour))
        GL.glBegin(GL.GL_POLYGON)
        for point in job.points:
            GL.glVertex2f(point[0], point[1])
        GL.glEnd()

    def render_RenderJobCircle(self, job):
        """ Render a circle. """
        GL.glColor3f(*self.colour_int_to_float(job.colour))
        if job.width == 0:
            GL.glBegin(GL.GL_TRIANGLE_FAN)
        else:
            GL.glLineWidth(job.width)
            GL.glBegin(GL.GL_LINE_LOOP)
        circumference = 2*math.pi*job.radius
        points = []
        npoi = max(int(math.sqrt(circumference)), 6)
        for i in range(0, npoi):
            angle = i/float(npoi) * math.pi * 2
            point = job.position + job.radius * Vec2d(math.cos(angle), math.sin(angle))
            GL.glVertex2f(point[0], point[1])
        GL.glEnd()

    def render_RenderJobText(self, job):
        """ Render some text. """
        text_surface = job.font.render(job.text, True, job.colour)
        texture = Texture.from_surface(text_surface)
        self.render_image(texture, texture.get_width(), texture.get_height(), job.position)
        texture.delete()

    def render_RenderJobAnimation(self, job):
        """ Render an animation. """
        width = job.length_to_screen(job.anim.frames.get_width())
        height = job.length_to_screen(job.anim.frames.get_height())
        self.render_image(
            job.anim.frames.get_frame(job.anim.timer),
            width,
            height,
            job.position,
            origin=Vec2d(width/2, height/2),
            orientation = math.radians(-job.orientation)
        )

    def render_RenderJobImage(self, job):
        """ Render an image. """
        width = job.length_to_screen(job.image.get_width())
        height = job.length_to_screen(job.image.get_height())
        self.render_image(job.image, width, height, job.position)

    def render_image(self, texture, width, height, position, **kwargs):
        """ Render an image. """
        texture.begin()
        self.render_quad(width, height, position, **kwargs)
        texture.end()

    def render_quad(self, width, height, position, **kwargs):
        """ Render a quad. """

        # Rotation about origin.
        orientation = 0
        if "orientation" in kwargs:
            orientation = kwargs["orientation"]

        # Origin position in local coordinates.
        origin = Vec2d(0, 0)
        if "origin" in kwargs:
            origin = kwargs["origin"]

        # Get quad corners in local coordinates, relative to position.
        tl = Vec2d(0, 0) - origin
        tr = Vec2d(width, 0) - origin
        br = Vec2d(width, height) - origin
        bl = Vec2d(0, height) - origin

        # Render the quad.
        GL.glBegin(GL.GL_QUADS)
        GL.glTexCoord2f(0, 1); GL.glVertex2f(*(position + tl.rotated(orientation)))
        GL.glTexCoord2f(0, 0); GL.glVertex2f(*(position + bl.rotated(orientation)))
        GL.glTexCoord2f(1, 0); GL.glVertex2f(*(position + br.rotated(orientation)))
        GL.glTexCoord2f(1, 1); GL.glVertex2f(*(position + tr.rotated(orientation)))
        GL.glEnd()

    def colour_int_to_float(self, colour):
        """ Convert colour to float format. """
        return (float(colour[0])/255, float(colour[1])/255, float(colour[2])/255)
