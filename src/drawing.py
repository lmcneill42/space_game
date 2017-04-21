""" Everything that draws itself on the screen is a drawable. A drawable is
a special kind of component that knows how to draw itself given a surface
and a camera. """

import pygame
import random

from .physics import *
from .behaviours import Hitpoints, Text, Thrusters, Shields, AnimationComponent, Weapon, Power

class Drawing(ComponentSystem):
    """ A class that manages a set of things that can draw themselves. """

    def __init__(self):
        ComponentSystem.__init__(self)
        self.__background_image = None
        self.__font = None

    def set_background(self, image_name):
        self.__background_image = self.game_services.get_resource_loader().load_image(image_name)

    def draw_background(self, camera):
        if self.__background_image is None:
            return
        screen = camera.surface()
        (image_width, image_height) = self.__background_image.get_size()
        (screen_width, screen_height) = screen.get_size()
        pos = camera.position
        x = int(pos.x)
        y = int(pos.y)
        start_i = -(x%image_width)
        start_j = -(y%image_width)
        for i in range(start_i, screen_width, image_width):
            for j in range(start_j, screen_height, image_height):
                screen.blit(self.__background_image, (i, j))


    def draw_graph(self, values, maximum, position, size, camera):
        """ Draw a graph from a list of values. """
        points = []
        for i, value in enumerate(values):
            x = position[0] + size[0] * (float(i)/(len(values)))
            y = position[1] + size[1] - size[1] * (value/float(maximum))
            points.append((x, y))
        if len(points) > 2:
            pygame.draw.rect(camera.surface(), (255, 255, 255), pygame.Rect(position, size), 1)
            pygame.draw.lines(camera.surface(), (200,200,200), False, points, 2)

    def draw_debug_info(self, camera):
        """ Draw the information. """

        # Check the debug level.
        if self.game_services.get_debug_level() <= 0:
            return

        # Load the font.
        if self.__font == None:
            self.__font = self.game_services.get_resource_loader().load_font(
                "res/fonts/nasdaqer/NASDAQER.ttf",
                12
            )

        game_info = self.game_services.get_info()

        # Draw the framerate.
        fps = self.__font.render("FPS (limited): %04.1f" % game_info.framerate, True, (255, 255, 255))
        camera.surface().blit(fps, (10, 10))

        # Draw the unlimited framerate.
        raw_fps = self.__font.render("FPS (raw): %04.1f" % game_info.raw_framerate, True, (255, 255, 255))
        camera.surface().blit(raw_fps, (10, 30))

        # Draw a graph of the framerate over time.
        self.draw_graph(game_info.framerates, 70, (10, 50), (100, 15), camera)

        # Draw the time ratio.
        time_ratio = self.__font.render("Time scale: %03.1f" % game_info.time_ratio, True, (255, 255, 255))
        camera.surface().blit(time_ratio, (10, 70))

        # Check the debug level.
        if self.game_services.get_debug_level() <= 1:
            return

        # Draw info about the entity under the cursor.
        cursor_position = Vec2d(pygame.mouse.get_pos())
        physics = self.get_system_by_type(Physics)
        ent = physics.get_entity_at(camera.screen_to_world(cursor_position))
        if ent is not None:
            x = 10
            y = 90
            def preview_ent(ent, x, y):
                ent_str = self.__font.render("Entity: %s" % ent, True, (255, 255, 255))
                camera.surface().blit(ent_str, (x, y))
                y += 20
                x += 20
                for component in self.game_services.get_entity_manager().get_all_components(ent):
                    comp_str = self.__font.render("%s" % component.__class__, True, (255, 255, 255))
                    camera.surface().blit(comp_str, (x, y))
                    y += 20
                for child in ent.get_children():
                    x,y = preview_ent(child, x, y)
                return (x, y)
            x, y = preview_ent(ent, x, y)

    def draw(self, camera):
        """ Draw the drawables in order of layer. """
        self.draw_background(camera)
        self.components = sorted(self.components, key = lambda x: x.level )
        for drawable in self.components:
            if not camera.check_bounds_world(drawable.estimate_bounds()):
                continue
            drawable.draw(camera)
        self.draw_debug_info(camera)

class Drawable(Component):
    """ Draws an entity on the screen. """

    def __init__(self, entity, game_services, config):
        """ Initialise the drawable """
        Component.__init__(self, entity, game_services, config)
        self.level = 0
        self.rect = None
        self.__text_drawer = None

    def manager_type(self):
        return Drawing

    def update(self, dt):
        """ Update our bounding box and kill timer. """
        if self.rect is None:
            anim = self.get_component(AnimationComponent)
            if anim is not None:
                self.rect = anim.get_anim().get_max_bounds()
        if self.rect is not None:
            self.rect.center = self.get_component(Body).position
        if self.__text_drawer is not None:
            self.__text_drawer.update(dt)

    def draw(self, camera):
        """ Draw the entity. """

        # If it's a body draw various things.
        self.draw_body(camera)

        # If it's text draw text.
        self.draw_text(camera)

    def draw_body(self, camera):
        """ Draw the body on the screen. """

        # Get the body
        body = self.get_component(Body)
        if body is None:
            return

        # Draw any animation.
        self.draw_animation(body, camera)

        # Draw any thrusters affecting the body.
        self.draw_thrusters(body, camera)

        # Draw hitpoints.
        self.draw_hitpoints(body, camera)

        # Draw shields.
        self.draw_shields(body, camera)

        # Draw lasers
        self.draw_lasers(body, camera)

    def draw_lasers(self, body, camera):
        """ Draw laser beams. """
        children = body.entity.get_children()
        for child in children:
            weapon = child.get_component(Weapon)
            if weapon is not None:
                if weapon.weapon_type == "beam":
                    if weapon.shooting and weapon.impact_point is not None:
                        p0 = camera.world_to_screen(body.position)
                        p1 = camera.world_to_screen(weapon.impact_point)
                        radius = weapon.config.get_or_default("radius", 2)
                        red = (255,100,100)
                        white = (255,255,255)
                        pygame.draw.line(camera.surface(),
                                         red,
                                         p0,
                                         p1,
                                         radius)
                        core_radius = radius//3
                        if core_radius > 0:
                            pygame.draw.line(camera.surface(),
                                             white,
                                             p0,
                                             p1,
                                             core_radius)
                        size = int(radius+random.random()*radius*2)
                        pygame.draw.circle(camera.surface(),
                                           red, 
                                           (int(p1.x), int(p1.y)),
                                           size)
                        pygame.draw.circle(camera.surface(),
                                           white, 
                                           (int(p1.x), int(p1.y)),
                                           size-2)
                                           

    def draw_shields(self, body, camera):
        """ Draw any shields the entity might have. """
        # Draw shields if we have them.
        shields = self.get_component(Shields)
        if shields is not None:
            width = int((shields.hp/float(shields.max_hp)) * 5)
            if width > 0:
                p = camera.world_to_screen(body.position)
                pygame.draw.circle(camera.surface(),
                                   (200, 220, 255),
                                   (int(p.x), int(p.y)),
                                   int(body.size*2),
                                   width)

    def draw_animation(self, body, camera):
        """ Draw an animation on the screen. """
        
        # See if there's an animation to draw.
        component = self.get_component(AnimationComponent)
        if component is None:
            return

        # Get the anim itself.
        anim = component.get_anim()

        # Draw the animation
        img = anim.frames[anim.timer.pick_index(len(anim.frames))]
        if (body.orientation != 0):
            img = pygame.transform.rotate(img, -body.orientation)
        if (camera.zoom != 0):
            size = Vec2d(img.get_size())* camera.zoom_factor
            img = pygame.transform.scale(img, (int(size[0]), int(size[1])))
        screen_pos = camera.world_to_screen(body.position) - Vec2d(img.get_rect().center)
        camera.surface().blit(img, screen_pos)

    def draw_thrusters(self, body, camera):
        """ Draw the thrusters affecting the body. """
        # If this body has thrusters then draw them.
        for thruster in body.thrusters():
            if thruster.on():
                pos = thruster.world_position(body)
                dir = thruster.world_direction(body)
                length = thruster.thrust() / 500.0
                poly = Polygon.make_bullet_polygon(pos, pos-(dir*length))
                poly.draw(camera)

    def draw_bar(self, arg_rect, fraction, col_back, col_0, col_1, camera):
        """ Draw a progress bar """
        rect = pygame.Rect(arg_rect)
        pygame.draw.rect(camera.surface(), col_back, rect)
        rect.inflate_ip(-4, -4)
        pygame.draw.rect(camera.surface(), col_0, rect)
        rect.width = int(fraction * rect.width)
        pygame.draw.rect(camera.surface(), col_1, rect)

    def draw_hitpoints(self, body, camera):
        """ Draw the entity's hitpoints, or a marker showing where it
        is if it's off screen. """

        # If this body has hitpoints draw a health bar
        hitpoints = self.get_component(Hitpoints)
        if hitpoints is None:
            return

        # Draw health bar if it's on screen. Otherwise draw marker.
        rect = pygame.Rect(0, 0, body.size*2, 6)
        rect.center = rect.center = camera.world_to_screen(body.position)
        rect.top = rect.top - (body.size*1.2)
        if camera.check_bounds_screen(rect):
            self.draw_bar(rect,
                          hitpoints.hp/float(hitpoints.max_hp),
                          (255, 255, 255),
                          (255, 0, 0),
                          (0, 255, 0),
                          camera)
            power = self.get_component(Power)
            if power is not None:
                rect.top += rect.height + 4
                self.draw_bar(rect,
                              power.power/float(power.capacity),
                              (255, 255, 255),
                              (100, 50, 0),
                              (255, 255, 0),
                              camera)
        else:
            (w, h) = camera.surface().get_size()
            rect.width = 5
            rect.height = 5
            rect.left = max(5, rect.left)
            rect.right = min(w-5, rect.right)
            rect.top = max(5, rect.top)
            rect.bottom = min(h-5, rect.bottom)
            pygame.draw.rect(camera.surface(), (255, 0, 0), rect)

    def draw_text(self, camera):
        """ Draw text using the text drawer. """
        if self.get_component(Text) is None:
            return
        if self.__text_drawer is None:
            self.__text_drawer = TextDrawer(self.entity, self.game_services)
        self.__text_drawer.draw(camera)

    def estimate_bounds(self):
        """ Return precomputed bounding box. """
        return self.rect

class TextDrawer(object):
    """ Draws text in the middle of the screen. Note that you don't set the text on the
    drawable, it gets stored in a Text component. This means that logic code doesn't need
    to mess with the drawable. """

    def __init__(self, entity, game_services):
        """Load the font."""
        self.entity = entity
        self.game_services = game_services
        text = self.entity.get_component(Text)
        self.__font = game_services.get_resource_loader().load_font(text.font_name(), text.large_font_size())
        self.__small_font = game_services.get_resource_loader().load_font(text.font_name(), text.small_font_size())
        self.__colour = text.font_colour()
        self.__text = None
        self.__image = None
        self.__warning = self.__small_font.render("WARNING", True, self.__colour)
        self.__level = 999
        self.__blink = text.blink()
        self.__blink_timer = Timer(text.blink_period())
        self.__visible = True
        self.__offs = 0
        self.__scroll_speed = 300
        self.__padding = 20

    def update(self, dt):
        """ Update: support blinking. """
        if self.__blink:
            if self.__blink_timer.tick(dt):
                self.__blink_timer.reset()
                self.__visible = not self.__visible

        self.__offs += self.__scroll_speed * dt
        self.__offs = self.__offs % (self.__warning.get_width()+self.__padding)

    def draw_warning(self, camera, forwards, y):
        # Draw scrolling warning
        if self.__blink:
            screen = camera.surface()
            (image_width, image_height) = self.__warning.get_size()
            (screen_width, screen_height) = screen.get_size()
            x = self.__offs
            if not forwards:
                x = -x
            start_i = -(x%(image_width+self.__padding))
            for i in range(int(start_i), screen_width, image_width + self.__padding):
                screen.blit(self.__warning, (i, y))
            rect = screen.get_rect()
            rect.height = 5
            rect.bottom = y-5
            pygame.draw.rect(camera.surface(), self.__colour, rect)
            rect.top=y+self.__warning.get_height()+5
            pygame.draw.rect(camera.surface(), self.__colour, rect)

    def draw(self, camera):
        """Draw the text to the screen."""

        # Try to obtain some text to draw.
        text = None
        text_component = self.entity.get_component(Text)
        if text_component is not None:
            text = text_component.text

        # Now cache the rendered text, if the text differs to what we had before. Note
        # that since the text can be null we have to handle that by unsetting the image.
        if self.__text != text:
            self.__image = None
            if text is not None:
                self.__image = self.__font.render(text, True, self.__colour)
            self.__text = text

        # Now draw the cached image, if we have one.
        if self.__visible and self.__image is not None:
            screen = camera.surface()
            pos = Vec2d(screen.get_rect().center) - Vec2d(self.__image.get_size()) / 2
            screen.blit(self.__image, (int(pos.x), int(pos.y)))

        if self.__image is not None:
            screen = camera.surface()
            pos = Vec2d(screen.get_rect().center) - Vec2d(self.__image.get_size()) / 2
            self.draw_warning(camera, True, int(pos.y-self.__warning.get_height()-10))
            self.draw_warning(camera, False, int(pos.y+self.__image.get_height()+10))

class Polygon(object):
    """ A polygon. Used to be used for bullets. """
    @classmethod
    def make_bullet_polygon(klass, a, b):
        perp = (a-b).perpendicular_normal() * (a-b).length * 0.1
        lerp = a + (b - a) * 0.1
        c = lerp + perp
        d = lerp - perp
        return Polygon((a,c,b,d,a))
    def __init__(self, points):
        self.points = [p for p in points]
        self.colour = (255, 255, 255)
    def draw(self, camera):
        transformed = [camera.world_to_screen(x) for x in self.points]
        pygame.draw.polygon(camera.surface(), self.colour, transformed)
