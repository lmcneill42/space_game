from pymunk.vec2d import Vec2d

import pygame

from .utils import ComponentSystem, Component
from .behaviours import Weapons, Weapon, Thrusters
from .physics import Body

class InputHandling(ComponentSystem):
    """ A system for input handlers: components that know how to deal
    with input. """
    def handle_input(self, event):
        self.garbage_collect()
        for handler in self.components:
            if handler.handle_input(event):
                return True
        return False

class InputHandler(Component):
    """ An input handling component. """
    def manager_type(self):
        return InputHandling
    def handle_input(self, event):
        return False

class PlayerInputHandler(InputHandler):
    """ Deals with input to the player's ship. """

    def __init__(self, entity, game_services, config):
        InputHandler.__init__(self, entity, game_services, config)

        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()

    def start_shooting(self, pos):
        """ Start shooting at a particular screen space point. """
        weapons = self.get_component(Weapons)
        if weapons is None:
            return
        weapon = weapons.get_weapon()
        if weapon is None:
            return
        weapon.start_shooting_screen(pos)

    def start_shooting_forwards(self):
        """ Start shooting ahead. """
        weapons = self.get_component(Weapons)
        if weapons is None:
            return
        weapon = weapons.get_weapon()
        if weapon is None:
            return
        weapon.start_shooting_coaxial()

    def stop_shooting(self):
        """ Stop the guns. """
        weapons = self.get_component(Weapons)
        if weapons is None:
            return
        weapon = weapons.get_weapon()
        if weapon is None:
            return
        weapon.stop_shooting()

    def is_shooting(self):
        """ Are the guns firing? If one is they both are. """
        weapons = self.get_component(Weapons)
        if weapons is None:
            return False
        weapon = weapons.get_weapon()
        if weapon is None:
            return False
        return weapon.shooting

    def zoom_in(self):
        """ Zoom the camera in."""
        self.game_services.get_camera().zoom += 1

    def zoom_out(self):
        """ Zoom the camera out. """
        self.game_services.get_camera().zoom -= 1

    def next_weapon(self):
        """ Cycle to the next weapon. """
        weapons = self.get_component(Weapons)
        if weapons is not None:
            weapons.next_weapon()

    def prev_weapon(self):
        """ Cycle to the previous weapon. """
        weapons = self.get_component(Weapons)
        if weapons is not None:
            weapons.prev_weapon()

    def handle_input(self, e):
        if InputHandler.handle_input(self, e):
            return True
        thrusters = self.get_component(Thrusters)
        if thrusters is None:
            return False
        def nothing(): pass
        kmap = {
            pygame.K_w: (lambda: thrusters.go_forwards(), lambda: thrusters.go_backwards()),
            pygame.K_a: (lambda: thrusters.go_left(), lambda: thrusters.go_right()),
            pygame.K_s: (lambda: thrusters.go_backwards(), lambda: thrusters.go_forwards()),
            pygame.K_d: (lambda: thrusters.go_right(), lambda: thrusters.go_left()),
            pygame.K_q: (lambda: thrusters.turn_right(), lambda: thrusters.turn_left()), # I swapped these two to make it work right.
            pygame.K_e: (lambda: thrusters.turn_left(), lambda: thrusters.turn_right()), # Please check it's now sensible.
            pygame.K_t: (nothing, lambda: self.zoom_in()),
            pygame.K_g: (nothing, lambda: self.zoom_out()),
            pygame.K_r: (nothing, lambda: self.next_weapon()),
            pygame.K_f: (nothing, lambda: self.prev_weapon()),
            pygame.K_SPACE: (lambda: self.start_shooting_forwards(), lambda: self.stop_shooting())
        }
        jsmap = {
            0: (lambda: self.start_shooting_forwards(), lambda: self.stop_shooting()),
            4: (lambda: thrusters.turn_left(), lambda: thrusters.turn_right()),
            5: (lambda: thrusters.turn_right(), lambda: thrusters.turn_left())
        }
        player = self.entity
        if e.type == pygame.KEYDOWN:
            if e.key in kmap:
                kmap[e.key][0]()
                return True
            # probably a bit of a messy way to do this, but I couldn't figure out how else... Hmm.
            elif e.key == pygame.K_ESCAPE:
                pygame.quit()
        elif e.type == pygame.KEYUP:
            if e.key in kmap:
                kmap[e.key][1]()
                return True
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.start_shooting_forwards()
            return True
        elif e.type == pygame.MOUSEBUTTONUP:
            self.stop_shooting()
            return True
        elif e.type == pygame.MOUSEMOTION:
            if self.is_shooting():
                self.start_shooting_forwards()
                return True
        elif e.type == pygame.JOYAXISMOTION:
            print( "axis: ", e.axis, e.value )
            pass
        elif e.type == pygame.JOYBALLMOTION:
            print( "ball: ", e.ball, e.rel )
            pass
        elif e.type == pygame.JOYBUTTONDOWN:
            print( "button: ", e.button )
            if e.button in jsmap:
                jsmap[e.button][0]()
                return True
            pass
        elif e.type == pygame.JOYBUTTONUP:
            print( "button: ", e.button )
            if e.button in jsmap:
                jsmap[e.button][1]()
                return True
            pass
        elif e.type == pygame.JOYHATMOTION:
            print( "hat: ", e.hat, e.value )
            thrusters.set_direction(Vec2d(e.value[0], -e.value[1]))
            return True
        return False
