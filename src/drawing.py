""" Draw the game using a Renderer. """

from pygame import Rect
import random

from .physics import Body, Thruster
from .behaviours import Hitpoints, Text, Shields, AnimationComponent, Weapon, Power
from .renderer import Renderer

class Drawing(object):
    """ An object that can draw the state of the game using a renderer. """

    def __init__(self, game_services):
        self.__entity_manager = game_services.get_entity_manager()
        self.__renderer = game_services.get_renderer()
        self.__resource_loader = game_services.get_resource_loader()
        self.__background_image = None
        self.__font = None
        self.__game_services = game_services

    def set_background(self, image_name):
        """ Load a background image. """
        self.__background_image = self.__resource_loader.load_image(image_name)

    def draw(self, camera):
        """ Draw the drawables in order of layer. """

        # Draw the background
        self.__renderer.add_job_background(self.__background_image)

        # Draw the things we can draw.
        self.__draw_animations(camera)
        self.__draw_thrusters(camera)
        self.__draw_shields(camera)
        self.__draw_lasers(camera)
        self.__draw_hitpoints(camera)
        self.__draw_text(camera)

        # Draw the debug info.
        self.__draw_debug_info(camera)

    def __draw_lasers(self, camera):
        """ Draw laser beams. """
        entities = self.__entity_manager.query(Weapon)
        for entity in entities:

            # We want weapons that are attached to a parent entity with a Body,
            # for position.
            weapon = entity.get_component(Weapon)
            parent = entity.get_parent()
            if parent is None:
                continue
            body = parent.get_component(Body)
            if body is None:
                continue

            # We only care about beam weapons that are currently firing.
            if weapon.weapon_type != "beam":
                continue
            if not weapon.shooting:
                continue
            if weapon.impact_point is None:
                continue

            # Ok, draw the laser beam.
            p0 = body.position
            p1 = weapon.impact_point
            radius = weapon.config.get_or_default("radius", 2)
            red = (255,100,100)
            white = (255,255,255)
            self.__renderer.add_job_line(
                p0,
                p1,
                colour=red,
                width=radius,
                brightness=2
            )
            core_radius = radius//3
            if core_radius > 0:
                self.__renderer.add_job_line(
                    p0,
                    p1,
                    colour=white,
                    width=core_radius,
                    brightness=2
                )

            # If something is being hit, draw an impact effect.
            dir = weapon.impact_normal
            if dir is not None:
                impact_size = radius * 15 * (1.0 + random.random()*0.6-0.8)
                poly1 = Polygon.make_bullet_polygon(p1, p1 + (dir * impact_size))
                self.__renderer.add_job_polygon(poly1, colour=white, brightness=5)
                poly2 = Polygon.make_bullet_polygon(p1, p1 + (dir * impact_size * 0.8))
                self.__renderer.add_job_polygon(poly2, colour=red, brightness=5)

    def __draw_shields(self, camera):
        """ Draw any shields the entity might have. """
        entities = self.__entity_manager.query(Body, Shields)
        for entity in entities:
            shields = entity.get_component(Shields)
            body = entity.get_component(Body)
            width = int((shields.hp/float(shields.max_hp)) * 5)
            if width > 0:
                self.__renderer.add_job_circle(
                    body.position,
                    int(body.size * 2),
                    colour=(100, 100, 255),
                    width=width,
                    brightness=2
                )

    def __draw_animation(self, camera):
        """ Draw an animation on the screen. """
        entities = self.__entity_manager.query(Body, AnimationComponent)
        for entity in entities:
            body = entity.get_component(Body)
            component = entity.get_component(AnimationComponent)
            anim = component.get_anim()
            self.__renderer.add_job_animation(
                -body.orientation,
                body.position,
                anim,
                brightness=component.config.get_or_default("brightness", 0.0)
            )

    def __draw_thrusters(self, camera):
        """ Draw the thrusters affecting the body. """
        entities = self.__entity_manager.query(Body)
        for entity in entities:
            body = entity.get_component(Body)
            for thruster in body.thrusters():
                if thruster.on():
                    pos = thruster.world_position(body)
                    dir = thruster.world_direction(body)
                    length = thruster.thrust() / 500.0
                    length *= (1.0 + random.random()*0.1 - 0.2)
                    poly = Polygon.make_bullet_polygon(pos, pos-(dir*length))
                    self.__renderer.add_job_polygon(
                        poly,
                        colour=(255, 255, 255),
                        brightness=2
                    )

    def __draw_hitpoints(self, camera):
        """ Draw the entity's hitpoints, or a marker showing where it
        is if it's off screen. """
        entities = self.__entity_manager.query(Body, Hitpoints)
        for entity in entities:
            body = entity.get_component(Body)
            hitpoints = entity.get_component(Hitpoints)

            # Draw health bar if it's on screen. Otherwise draw marker.
            rect = Rect(0, 0, body.size*2, 6)
            rect.center = rect.center = camera.world_to_screen(body.position)
            rect.top = rect.top - (body.size*1.2)
            self.__draw_bar(
                camera,
                rect,
                hitpoints.hp/float(hitpoints.max_hp),
                (255, 255, 255),
                (255, 0, 0),
                (0, 255, 0)
            )

            # Sneakily draw a power bar as well if the entity has it.
            power = entity.get_component(Power)
            if power is not None:
                rect.top += rect.height + 4
                self.__draw_bar(
                    camera,
                    rect,
                    power.power/float(power.capacity),
                    (255, 255, 255),
                    (100, 50, 0),
                    (255, 255, 0)
                )

    def __draw_text(self, camera):
        """ Draw text on the screen. """

        entities = self.__entity_manager.query(Text)
        for entity in entities:
            component = entity.get_component(Text)

            # Cache an image of the rendered text.
            if component.cached_image is None:
                component.cached_image = self.__renderer.compatible_image_from_text(
                    component.text,
                    font,
                    component.colour
                )

            # Render the text.
            if component.visible:
                pos = Vec2d(self.__renderer.screen_rect().center) \
                        - Vec2d(self.__image.get_size()) / 2
                self.__renderer.add_job_image(
                    pos,
                    component.cached_image,
                    coords=Renderer.COORDS_SCREEN,
                    brightness=0.25
                )

            # Get positions of the 'WARNING' strips
            pos = Vec2d(self.__renderer.screen_rect().center) \
                    - Vec2d(component.cached_image.get_size()) / 2
            y0 = int(pos.y-component.cached_warning.get_height()-10)
            y1 = int(pos.y+component.cached_image.get_height()+10)

            # Draw a scrolling warning.
            if component.blink:

                # Cache an image of the rendered 'warning' string.
                if component.cached_warning is None:
                    component.cached_warning = self.__renderer.compatible_image_from_text(
                        "WARNING",
                        small_font,
                        component.colour
                    )

                # Draw a row of 'warnings' at the top and bottom.
                for (forwards, y) in ((True, y0), (False, y1)):

                    # Draw a row of 'WARNING's.
                    (image_width, image_height) = component.cached_warning.get_size()
                    (screen_width, screen_height) = self.__renderer.screen_size()
                    x = component.offset
                    if not forwards:
                        x = -x
                    start_i = -(x%(image_width+component.padding))
                    for i in range(int(start_i), screen_width, image_width + component.padding):
                        self.__renderer.add_job_image(
                            (i, y),
                            component.cached_warning,
                            coords=Renderer.COORDS_SCREEN,
                            brightness=0.25
                        )

                    # Draw the top bar.
                    rect = self.__renderer.screen_rect()
                    rect.height = 5
                    rect.bottom = y-5
                    self.__renderer.add_job_rect(
                        rect,
                        colour=component.colour,
                        coords=Renderer.COORDS_SCREEN,
                        brightness=0.25
                    )

                    # Draw the bottom bar.
                    rect.top=y+component.cached_warning.get_height()+5
                    self.__renderer.add_job_rect(
                        rect,
                        colour=component.colour,
                        coords=Renderer.COORDS_SCREEN,
                        brightness=0.25
                    )

    def __draw_debug_info(self, camera):
        """ Draw the information. """

        # Check the debug level.
        if self.__game_services.get_debug_level() <= 0:
            return

        # Load the font.
        if self.__font == None:
            self.__font = self.__resource_loader.load_font(
                "res/fonts/nasdaqer/NASDAQER.ttf",
                12
            )

        game_info = self.__game_services.get_info()

        # Draw the framerate.
        self.__renderer.add_job_text(
            self.__font,
            "FPS (limited): %04.1f" % game_info.framerate,
            (10, 10)
        )

        # Draw the unlimited framerate.
        self.__renderer.add_job_text(
            self.__font,
            "FPS (raw): %04.1f" % game_info.raw_framerate,
            (10, 30)
        )

        # Draw a graph of the framerate over time.
        self.__draw_graph(
            camera,
            game_info.framerates,
            70,
            (10, 50),
            (100, 15)
        )

        # Draw the time ratio.
        self.__renderer.add_job_text(
            self.__font,
            "Time scale: %03.1f" % game_info.time_ratio,
            (10, 70)
        )

    def __draw_bar(self, camera, arg_rect, fraction,
                   col_back, col_0, col_1):
        """ Draw a progress bar """

        # The background
        self.__renderer.add_job_rect(
            arg_rect,
            colour=col_back,
            coords=Renderer.COORDS_SCREEN,
            brightness=0.2
        )

        # The empty portion.
        rect = Rect(arg_rect)
        rect.inflate_ip(-4, -4)
        self.__renderer.add_job_rect(
            rect,
            colour=col_0,
            coords=Renderer.COORDS_SCREEN,
            brightness=0.2
        )

        # The full portion.
        rect.width = int(fraction * rect.width)
        self.__renderer.add_job_rect(
            rect,
            colour=col_1,
            coords=Renderer.COORDS_SCREEN,
            brightness=0.2
        )

    def __draw_graph(self, camera, values, maximum, position, size):
        """ Draw a graph from a list of values. """
        points = []
        for i, value in enumerate(values):
            x = position[0] + size[0] * (float(i)/(len(values)))
            y = position[1] + size[1] - size[1] * (value/float(maximum))
            points.append((x, y))
        if len(points) > 2:
            self.__renderer.add_job_rect(
                Rect(position, size),
                width=1,
                colour=(255, 255, 255),
                coords=Renderer.COORDS_SCREEN
            )
            self.__renderer.add_job_lines(
                points,
                width=2,
                colour=(200, 200, 200),
                coords=Renderer.COORDS_SCREEN
            )
