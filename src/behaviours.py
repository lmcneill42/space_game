""" Object behaviours for the game and entitys composed out of them.

See utils.py for the overall scheme this fits into.

"""

from .ecs import Component, EntityRef
from .physics import Body, Physics, CollisionHandler, CollisionResult, Thruster
from .renderer import View
from .utils import Timer, Vec2d

import random
import math


class Tracking(Component):
    """ Tracks something on the opposite team. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.tracked = EntityRef(None, Body)
        self.track_type = config.get_or_default("track_type", "team")


class FollowsTracked(Component):
    """ Follows the Tracked entity. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.follow_type = config.get_or_default("follow_type", "accelerate")


class ShootsAtTracked(Component):
    """ If the entity has Weapons it shoots them at the Tracked entity. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.fire_timer = Timer(config.get_or_default("fire_period", 1))
        self.fire_timer.advance_to_fraction(0.8)
        self.burst_timer = Timer(config.get_or_default("burst_period", 1))
        self.can_shoot = False


class Weapon(Component):
    """ The entity is a weapon that e.g. shoots bullets. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.owner = EntityRef(None)
        self.shooting_at = None
        self.shot_timer = 0
        self.weapon_type = self.config.get_or_default("type", "projectile_thrower")
        self.impact_point = None
        self.impact_normal = None


class LaunchesFighters(Component):
    """ Launches fighters periodically. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.spawn_timer = Timer(config["spawn_period"])


class KillOnTimer(Component):
    """ For objects that should be destroyed after a limited time. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.lifetime = Timer(config["lifetime"])


class ExplodesOnDeath(Component):
    """ For objects that spawn an explosion when they die. """
    pass


class EndProgramOnDeath(Component):
    """ If the entity this is attached to is destroyed, the program will exit. """
    pass


class Hitpoints(Component):
    """ Object with hitpoints, can be damaged. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"]


class Power(Component):
    """ The entity stores / produces power. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.capacity = config["capacity"]
        self.power = self.capacity
        self.recharge_rate = config["recharge_rate"]
        self.overloaded = False
        self.overload_timer = Timer(config.get_or_default("overload_time", 5))


class Shields(Component):
    """ The entity has shields that protect it from damage. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"] # Rendundant, but code uses this.
        self.recharge_rate = config["recharge_rate"]
        self.overloaded = False
        self.overload_timer = Timer(config.get_or_default("overload_time", 5))


class DamageOnContact(Component):
    """ The entity damages other entities on contact. """
    pass


class Team(Component):
    """ The entity is on a team. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.team = config.get_or_none("team")


class Text(Component):
    """ The entity contains text. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.text = config.get_or_default("text", "Hello, world!")
        self.blink_timer = Timer(self.blink_period())
        self.visible = True
        self.offs = 0
        self.scroll_speed = 300
        self.padding = 20
        self.image = None
        self.warning = None
        self.colour = (255, 255, 255)
        self.warning = None
        self.image = None
        self.font_name = self.config["font_name"]
        self.small_font_size = config.get_or_default("small_font_size", 14)
        self.large_font_size = config.get_or_default("font_size", 32)
        colour = self.config.get_or_default("font_colour", {"red":255, "green":255, "blue":255})
        self.font_colour = (colour["red"], colour["green"], colour["blue"])
        self.blink = self.config.get_or_default("blink", 0)
        self.blink_period = self.config.get_or_default("blink_period", 1)


class AnimationComponent(Component):
    """ The entity has an animation. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.anim = game_services.get_resource_loader().load_animation(config["anim_name"])


class Thrusters(Component):
    """ The entity has thrusters & a target direction. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.direction = Vec2d(0, 0)
        self.turn = 0


class Turret(Component):
    """ The entity is a turret affixed to another entity. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, game_services, config)
        self.position = position
        self.weapon = EntityRef(None, Weapon)


class Turrets(Component):
    """ The entity has a set of turrets. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.turrets = []


class Camera(Component):
    """ A camera, which drawing is done in relation to. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        renderer = game_services.get_renderer()
        self.position = Vec2d(0, 0)
        self.max_shake = 20
        self.damping_factor = 10
        self.shake = 0
        self.vertical_shake = 0
        self.horizontal_shake = 0
        self.tracking = EntityRef(None, Body)
        self.zoom = 1
        self.screen_diagonal = (Vec2d(renderer.screen_size())/2).length
