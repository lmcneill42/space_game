""" Object behaviours for the game and entitys composed out of them.

See utils.py for the overall scheme this fits into.

"""

from pymunk.vec2d import Vec2d
from .utils import Component, Timer
from .physics import Body, Physics, CollisionHandler, CollisionResult, Thruster

import random
import math
        
class FollowsTracked(Component):

    def update(self, dt):
        """ Follows the tracked body. """

        body = self.get_component(Body)
        player_body = self.get_component(Tracking).get_tracked()

        if body is None or player_body is None:
            return
        
        displacement = player_body.position - body.position
        rvel = player_body.velocity - body.velocity
        target_dist = self.config["desired_distance_to_player"]

        # distality is a mapping of distance onto the interval [0,1) to
        # interpolate between two behaviours
        distality = 1 - 2 ** ( - displacement.length / target_dist )
        direction = ( 1 - distality ) * rvel.normalized() + distality * displacement.normalized()

        # Determine the fraction of our thrust to apply. This is governed by
        # how far away the target is, and how far away we want to be.
        frac = min(max(displacement.length / target_dist, rvel.length/200), 1)

        # Apply force in the interpolated direction.
        thrust = body.mass * self.config["acceleration"]
        force = frac * thrust * direction
        body.force = force

class ShootingAt(object):
    """ An object that defines a direction in which to shoot. """
    def __init__(self):
        pass
    def direction(self):
        pass

class ShootingAtScreen(object):
    """ Shooting at a point in screen space. """
    def __init__(self, pos, body, camera):
        self.__pos = pos
        self.__camera = camera
        self.__body = body
    def direction(self):
        return (self.__camera.screen_to_world(self.__pos) - self.__body.position).normalized()

class ShootingAtWorld(object):
    """ Shooting at a point in world space. """
    def __init__(self, pos, body):
        self.__pos = pos
        self.__body = body
    def direction(self):
        return (self.__pos - self.__body.position).normalized()

class ShootingAtDirection(object):
    """ Shooting in a particular direction. """
    def __init__(self, direction):
        self.__direction = direction
    def direction(self):
        return self.__direction

class ShootingAtBody(object):
    """ Shooting at a body. """
    def __init__(self, from_body, to_body):
        self.__from_body = from_body
        self.__to_body = to_body
    def direction(self):
        return (-self.__to_body.position + self.__from_body.position).normalized()

class ShootingAtCoaxial(object):
    """ Shooting in line with a body. """
    def __init__(self, from_body):
        self.__from_body = from_body
    def direction(self):
        return Vec2d(0, -1).rotated(math.radians(self.__from_body.orientation))

class Weapons(Component):
    """ An entity with the 'weapons' component manages a set of child entities
    which have the 'weapon' component. """

    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)

        # Initialise the weapons.
        self.__weapons = []
        weapons = config.get_or_default("weapons", [])
        for weapon_config in weapons:
            self.__weapons.append(self.create_entity(weapon_config, parent=self.entity))

        # Set the current weapon.
        self.__current_weapon = -1
        if len(self.__weapons) > 0:
            self.__current_weapon = 0

        # Auto firing.
        self.autofire = config.get_or_default("auto_fire", False)
        self.fire_timer = Timer(config.get_or_default("fire_period", 1))
        self.fire_timer.advance_to_fraction(0.8)
        self.burst_timer = Timer(config.get_or_default("burst_period", 1))
        self.can_shoot = False 

    def get_weapon(self):
        """ Get the weapon component of our sub-entity. """
        if self.__current_weapon < 0:
            return None
        return self.__weapons[self.__current_weapon].get_component(Weapon)

    def next_weapon(self):
        """ Cycle to the next weapon. """
        if self.__current_weapon < 0:
            return
        was_shooting = self.__weapons[self.__current_weapon].get_component(Weapon).shooting
        if was_shooting: self.__weapons[self.__current_weapon].get_component(Weapon).stop_shooting()
        self.__current_weapon = (self.__current_weapon+1)%len(self.__weapons)
        if was_shooting : self.__weapons[self.__current_weapon].get_component(Weapon).start_shooting_coaxial()

    def prev_weapon(self):
        """ Cycle to the previous weapon. """
        if self.__current_weapon < 0:
            return
        was_shooting = self.__weapons[self.__current_weapon].get_component(Weapon).shooting
        if was_shooting: self.__weapons[self.__current_weapon].get_component(Weapon).stop_shooting()
        self.__current_weapon = (self.__current_weapon-1)%len(self.__weapons)
        if was_shooting : self.__weapons[self.__current_weapon].get_component(Weapon).start_shooting_coaxial()

    def update(self, dt):
        """ Update the shooting bullet. """

        if not self.autofire:
            return

        body = self.get_component(Body)
        if body is None:
            return
        
        guns = self.get_component(Weapons)
        if guns is None:
            return

        gun = guns.get_weapon()
        if gun is None:
            return

        tracking = self.get_component(Tracking)
        if tracking is None:
            return

        tracked_body = tracking.get_tracked()
        if tracked_body is None:
            return

        # Point at the object we're tracking. Note that in future it would be
        # good for this to be physically simulated, but for now we just hack
        # it in...
        direction = (tracked_body.position - body.position).normalized()
        body.orientation = 90 + direction.angle_degrees

        # Shoot at the object we're tracking.
        if not gun.shooting:
            if not self.can_shoot and self.fire_timer.tick(dt):
                self.fire_timer.reset()
                self.can_shoot = True
            if self.can_shoot:
                (hit_body, hit_point) = body.hit_scan()
                if hit_body == tracked_body:
                    self.can_shoot = False
                    gun.start_shooting_at_body(tracked_body)
        else:
            if self.burst_timer.tick(dt):
                self.burst_timer.reset()
                gun.stop_shooting()

class Weapon(Component):
    """ Something that knows how to spray bullets.

    A weapon is intended to be a component on an entity that represents
    the weapon-entity.  This should be a child of the entity that 'has' a
    weapon.  It is the parent entity that needs to have a position in space
    etc.  So you have

    e0 (player) <-------- e1 (weapon)
    ^                     ^
    |                     |
    Body                  Weapon
    ...                   ...
    """

    def __init__(self, entity, game_services, config):
        """ Inject dependencies and set up default parameters. """
        Component.__init__(self, entity, game_services, config)
        self.shooting_at = None
        self.shot_timer = 0
        self.weapon_type = self.config.get_or_default("type", "projectile_thrower")
        self.impact_point = None

    def __get_body(self):
        """ Get the body of the entity with the weapon. """
        if self.entity.parent is None:
            return None
        return self.entity.parent.get_component(Body)

    def __get_team(self):
        """ Get the team our parent is on. """
        if self.entity.parent is None:
            return None
        return self.entity.parent.get_component(Team).get_team()

    def __get_power(self):
        """ Get the power component. """
        if self.entity.parent is None:
            return None
        return self.entity.parent.get_component(Power)

    def start_shooting_coaxial(self):
        self.shooting_at = ShootingAtCoaxial(self.__get_body())

    def start_shooting_dir(self, direction):
        self.shooting_at = ShootingAtDirection(direction)

    def start_shooting_world(self, at):
        """ Start shooting at a point in world space. """
        self.shooting_at = ShootingAtWorld(at, self.__get_body())

    def start_shooting_at_body(self, body):
        """ Start shooting at a body. """
        self.shooting_at = ShootingAtBody(body, self.__get_body())

    def start_shooting_screen(self, at):
        """ Start shooting at a point in screen space. """
        self.shooting_at = ShootingAtScreen(at, self.__get_body(), self.game_services.get_camera())

    def stop_shooting(self):
        """ Stop spraying bullets. """
        self.shooting_at = None

    @property
    def shooting(self):
        return self.shooting_at is not None

    def update(self, dt):
        """ Create bullets if shooting. Our rate of fire is governed by a timer. """

        # Count down to shootin.
        if self.shot_timer > 0:
            self.shot_timer -= dt


        # If we're shooting, let's shoot some bullets!
        if self.shooting:

            if self.weapon_type == "projectile_thrower":
                self.shoot_bullet()

            elif self.weapon_type == "beam":

                power = self.__get_power()
                if power is None or not power.consume(self.config["power_usage"] * dt):
                    self.stop_shooting()
                else:

                    body = self.__get_body()

                    # Figure out if the laser has hit anything.
                    (hit_body, self.impact_point) = body.hit_scan(Vec2d(0, 0),
                                                                  Vec2d(0, -1),
                                                                  self.config["range"],
                                                                  self.config["radius"])

                    # If we hit something, damage it.
                    if hit_body is not None:
                        apply_damage_to_entity(self.config["damage"]*dt, hit_body.entity)

            else:
                # Unknown weapon style.
                pass

    def shoot_bullet(self):
        """ Shoot a bullet, for projectile thrower type weapons. """

        # If it's time, shoot a bullet and rest the timer. Note that
        # we can shoot more than one bullet in a time step if we have
        # a high enough rate of fire.
        while self.shot_timer <= 0:

            # These will be the same for each shot, so get them here...
            body = self.__get_body()
            shooting_at_dir = self.shooting_at.direction()

            # Update the timer.
            self.shot_timer += 1.0/self.config["shots_per_second"]

            # Can't spawn bullets if there's nowhere to put them!
            if body is None:
                return

            # Position the bullet somewhere sensible.
            separation = body.size*2
            bullet_position = Vec2d(body.position) + shooting_at_dir * separation

            # Work out the muzzle velocity.
            muzzle_velocity = shooting_at_dir * self.config["bullet_speed"]
            spread = self.config["spread"]
            muzzle_velocity.rotate_degrees(random.random() * spread - spread)
            bullet_velocity = body.velocity+muzzle_velocity

            # Play a sound.
            shot_sound = self.config.get_or_none("shot_sound")
            if shot_sound is not None:
                self.game_services.get_camera().play_sound(body, shot_sound)

            # Create the bullet.
            self.create_entity(self.config["bullet_config"],
                                    parent=self.entity,
                                    team=self.__get_team(),
                                    position=bullet_position,
                                    velocity=bullet_velocity,
                                    orientation=shooting_at_dir.normalized().get_angle_degrees()+90)

class Tracking(Component):
    """ Tracks something on the opposite team. """

    # Note: Camera does a kind of tracking, but with an explicitly
    # specified object, not the closest object on the other team. If
    # the concept of multiple tracking behaviours were introduced, the
    # camera could use the Tracking component.

    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.__tracked_body = None

    def get_tracked(self):
        """ Get the tracked body. """
        if self.__tracked_body is not None:
            if self.__tracked_body.is_garbage():
                self.__tracked_body = None
        return self.__tracked_body

    def reset_tracking(self):
        """ Stop tracking the current body and find something else. """
        self.__tracked_body = None

    def towards_tracked(self):
        """ Get the direction towards the tracked body. """
        body = self.get_tracked()
        if body is None:
            return Vec2d(0, 1)
        return (body.position - self.get_component(Body).position).normalized()

    def update(self, dt):
        """ Update the tracking. """

        # Ensure the object we're tracking still exists.
        if self.__tracked_body is not None:
            if self.__tracked_body.is_garbage():
                self.__tracked_body = None

        # Update tracking.
        if self.__tracked_body is None:

            # Find the closest object we don't like.
            self_team = self.get_component(Team)
            def f(body):
                team = body.get_component(Team)
                if self_team is None:
                    return False
                if team is None:
                    return False
                return not team.on_same_team(self_team)
            closest = self.get_system_by_type(Physics).closest_body_with(
                self.get_component(Body).position,
                f
            )
            if closest:
                self.__tracked_body = closest

class LaunchesFighters(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.spawn_timer = Timer(config["spawn_period"])
    def update(self, dt):
        if self.spawn_timer.tick(dt):
            self.spawn_timer.reset()
            self.spawn()
    def spawn(self):
        for i in range(self.config["num_fighters"]):
            direction = self.get_component(Tracking).towards_tracked()
            spread = self.config["takeoff_spread"]
            direction.rotate_degrees(spread*random.random()-spread/2.0)
            body = self.get_component(Body)
            child = self.create_entity(self.config["fighter_config"],
                                            team=self.get_component(Team).get_team(),
                                            position=body.position,
                                            velocity=body.velocity + direction * self.config["takeoff_speed"])

class KillOnTimer(Component):
    """ For objects that should be destroyed after a limited time. """
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.lifetime = Timer(config["lifetime"])
    def update(self, dt):
        if self.lifetime.tick(dt):
            self.entity.kill()

class ExplodesOnDeath(Component):
    """ For objects that spawn an explosion when they die. """
    def on_object_killed(self):
        body = self.get_component(Body)
        explosion = self.create_entity(self.config["explosion_config"],
                                            position=body.position,
                                            velocity=body.velocity)
        shake_factor = self.config.get_or_default("shake_factor", 1)
        camera = self.game_services.get_camera()
        camera.apply_shake(shake_factor, body.position)

        # Play a sound.
        sound = self.config.get_or_none("sound")
        if sound is not None:
            camera.play_sound(body, sound)

class EndProgramOnDeath(Component):
    """ If the entity this is attached to is destroyed, the program will exit. """
    def on_object_killed(self):
        self.game_services.end_game()

class Hitpoints(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"] # Rendundant, but code uses this.

    def receive_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.entity.kill()

class Power(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.capacity = config["capacity"]
        self.power = self.capacity
        self.recharge_rate = config["recharge_rate"]
    def update(self, dt):
        self.power = min(self.capacity, self.power + self.recharge_rate * dt)
    def consume(self, amount):
        if amount <= self.power:
            self.power -= amount
            return amount
        return 0
        
class Shields(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.hp = self.config["hp"]
        self.max_hp = self.config["hp"] # Rendundant, but code uses this.
        self.recharge_rate = config["recharge_rate"]
    def update(self, dt):
        power = self.get_component(Power)
        if power is None:
            self.hp = 0
        else:
            self.hp = min(self.max_hp, self.hp + power.consume(self.recharge_rate * dt))

    def mitigate_damage(self, amount):
        self.hp -= amount
        ret = 0
        if self.hp < 0:
            ret = -self.hp
            self.hp = 0
        return ret

def apply_damage_to_entity(damage, entity):
    """ Apply damage to an object we've hit. """
    shields = entity.get_component(Shields) 
    if shields is not None:
        damage = shields.mitigate_damage(damage)
    hitpoints = entity.get_component(Hitpoints)
    if hitpoints is not None:
        hitpoints.receive_damage(damage)

class DamageOnContact(Component):
    def match_velocities(self, entity):
        """ Match speeds with the given entity. """
        b1 = self.get_component(Body)
        b2 = entity.get_component(Body)
        if b1 is not None and b2 is not None:
            b1.velocity = b2.velocity
    def apply_damage(self, entity):
        """ Apply damage to the entity and kill ourselves if necessary. """
        damage = self.config["damage"]
        if self.config.get_or_default("destroy_on_hit", True):
            # If our entity is about to die we might be about to spawn an
            # explosion. If that's the case it should be travelling at the
            # same speed as the thing we hit. So match velocities before
            # our entity is killed.
            self.match_velocities(entity)
            self.entity.kill()
        apply_damage_to_entity(damage, entity)

class DamageCollisionHandler(CollisionHandler):
    """ Collision handler to apply bullet damage. """
    def __init__(self):
        CollisionHandler.__init__(self, DamageOnContact, Hitpoints)
    def handle_matching_collision(self, dmg, hp):
        if hp.entity.is_ancestor(dmg.entity):
            return CollisionResult(False, False)
        dmg.apply_damage(hp.entity)
        return CollisionResult(True, True)

class Team(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.__team = config.get_or_none("team")
    def setup(self, **kwargs):
        if "team" in kwargs:
            self.__team = kwargs["team"]
    def get_team(self):
        return self.__team
    def set_team(self, team):
        self.__team = team
    def on_same_team(self, that):
        return self.__team == None or that.__team == None or self.__team == that.__team

class Text(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.text = config.get_or_default("text", "Hello, world!")
    def setup(self, **kwargs):
        Component.setup(self, **kwargs)
        if "text" in kwargs:
            self.text = kwargs["text"]
    def font_name(self):
        return self.config["font_name"]
    def small_font_size(self):
        return self.config.get_or_default("small_font_size", 14)
    def large_font_size(self):
        return self.config.get_or_default("font_size", 32)
    def font_colour(self):
        colour = self.config.get_or_default("font_colour", {"red":255, "green":255, "blue":255})
        return (colour["red"], colour["green"], colour["blue"])
    def blink(self):
        return self.config.get_or_default("blink", 0)
    def blink_period(self):
        return self.config.get_or_default("blink_period", 1)

class AnimationComponent(Component):
    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.__anim = game_services.get_resource_loader().load_animation(config["anim_name"])
    def update(self, dt):
        if self.__anim.tick(dt):
            if self.config.get_or_default("kill_on_finish", 0):
                self.entity.kill()
            else:
                self.__anim.reset()
    def get_anim(self):
        return self.__anim

class Thrusters(Component):
    """ Thruster component. This allows an entity with a body to move itself.
    Eventually I intend to have the thrusters be configurable, but for now its
    hard coded."""

    def __init__(self, entity, game_services, config):
        """ Initialise - set up the enginges. """
        Component.__init__(self, entity, game_services, config)
        self.__direction = Vec2d(0, 0)
        self.__dir_right = Vec2d(1, 0)
        self.__dir_backwards = Vec2d(0, 1)
        self.__turn = 0

    def setup(self, **kwargs):
        Component.setup(self, **kwargs)

        # Note: this is hard coded for now, but in future we could specify the
        # thruster layout in the config.
        body = self.get_component(Body)
        body.add_thruster(Thruster(Vec2d(-20, -20), Vec2d( 1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d(-20,  20), Vec2d( 1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d( 20, -20), Vec2d(-1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d( 20,  20), Vec2d(-1,  0), self.config["max_thrust"] / 8))
        body.add_thruster(Thruster(Vec2d(  0, -20), Vec2d( 0,  1), self.config["max_thrust"] / 4))
        body.add_thruster(Thruster(Vec2d(  0,  20), Vec2d( 0, -1), self.config["max_thrust"]    ))

    def go_forwards(self):
        self.__direction -= self.__dir_backwards

    def go_backwards(self):
        self.__direction += self.__dir_backwards

    def go_left(self):
        self.__direction -= self.__dir_right

    def go_right(self):
        self.__direction += self.__dir_right

    def set_direction(self, direction):
        self.__direction = Vec2d(direction)

    def turn_left(self):
        self.__turn += 1

    def turn_right(self):
        self.__turn -= 1

    def update(self, dt):
        """ Update the engines, and automatically counteract spin."""

        # Cant do much without a body.
        body = self.get_component(Body)
        if body is None:
            return

        # Automatically counteract spin.
        turn = self.__turn
        if turn == 0 and self.__direction.x == 0:
            eps = 10 # LOLOLOL
            if body.angular_velocity > eps:
                turn = -1
            elif body.angular_velocity < -eps:
                turn = 1

        # Fire the right thrusters on the body.
        body.fire_correct_thrusters(self.__direction, turn)

class WaveSpawner(Component):
    """ Spawns waves of enemies. """

    def __init__(self, entity, game_services, config):
        Component.__init__(self, entity, game_services, config)
        self.wave = 1
        self.spawned = []
        self.message = None
        self.done = False

    def update(self, dt):
        """ Update the spawner. """
        Component.update(self, dt)

        # Check for end condition and show game ending message if so.
        if self.done:
            return
        elif self.player_is_dead() or self.max_waves():
            self.done = True
            txt = "GAME OVER"
            if self.max_waves():
                txt = "VICTORY"
            message = self.create_entity("endgame_message.txt", text=txt)

        # If the wave is dead and we're not yet preparing (which displays a timed message) then
        # start preparing a wave.
        if self.wave_is_dead() and self.message is None:
            self.prepare_for_wave()

        # If we're prepared to spawn i.e. the wave is dead and the message has gone, spawn a wave!
        if self.prepared_to_spawn():
            self.spawn_wave()

    def player_is_dead(self):
        """ Check whether the player is dead. """
        player = self.game_services.get_player()
        return player.is_garbage

    def spawn_wave(self):
        """ Spawn a wave of enemies, each one harder than the last."""
        player = self.game_services.get_player()
        player_body = player.get_component(Body)
        self.wave += 1
        for i in range(self.wave-1):
            enemy_type = random.choice(("enemies/destroyer.txt",
                                        "enemies/carrier.txt"))
            rnd = random.random()
            x = 1 - rnd*2
            y = 1 - (1-rnd)*2
            enemy_position = player_body.position + Vec2d(x, y)*500
            self.spawned.append(self.create_entity(enemy_type,
                                                        position=enemy_position,
                                                        team="enemy"))

    def wave_is_dead(self):
        """ Has the last wave been wiped out? """
        self.spawned = list( filter(lambda x: not x.is_garbage, self.spawned) )
        return len(self.spawned) == 0

    def prepare_for_wave(self):
        """ Prepare for a wave. """
        self.message = self.create_entity("update_message.txt",
                                               text="WAVE %s PREPARING" % self.wave)

    def prepared_to_spawn(self):
        """ Check whether the wave is ready. """
        if self.message is None or not self.wave_is_dead():
            return False
        if self.message.is_garbage:
            self.message = None
            return True
        return False

    def max_waves(self):
        """ Check whether the player has beaten enough waves. """
        return self.wave == 10

class HardPoint(object):
    """ A slot that can contain a weapon. """

    def __init__(self, position):
        """ Initialise the hardpoint. """
        self.__position = position
        self.__weapon = None

    def set_turret(self, weapon_entity, body_to_add_to):
        """ Set the weapon, freeing any existing weapon. """

        # If there is already a weapon then we need to delete it.
        if self.__weapon is not None:
            self.__weapon.kill()

        # Ok, set the new weapon.
        self.__weapon = weapon_entity

        # If the weapon has been unset, then our work is done.
        if self.__weapon is None:
            return

        # If a new weapon has been added then pin it to our body.
        weapon_body = self.__weapon.get_component(Body)
        point = body_to_add_to.local_to_world(self.__position)
        weapon_body.position = point
        weapon_body.velocity = body_to_add_to.velocity
        weapon_body.pin_to(body_to_add_to)

class Turrets(Component):

    def __init__(self, entity, game_services, config):
        """ Initialise the turrets. """
        Component.__init__(self, entity, game_services, config)
        self.__hardpoints = []
        hardpoints = config.get_or_default("hardpoints", [])
        for hp in hardpoints:
            if not "x" in hp or not "y" in hp:
                continue
            self.__hardpoints.append(HardPoint(Vec2d(hp["x"], hp["y"])))
            weapon_config = "enemies/turret.txt"
            if "weapon_config" in hp:
                weapon_config = hp["weapon_config"]
            self.set_turret(len(self.__hardpoints)-1, weapon_config)

    def num_hardpoints(self):
        """ Get the number of hardpoints. """
        return len(self.__hardpoints)

    def set_turret(self, hardpoint_index, weapon_config_name):
        """ Set the weapon on a hardpoint. Note that the weapon is an actual
        entity, which is set up as a child of the entity this component is
        attached to. It is assumed to have a Body component, which is pinned
        to our own Body."""
        entity = self.create_entity(weapon_config_name,
                                         parent=self.entity,
                                         team=self.get_component(Team).get_team())
        self.__hardpoints[hardpoint_index].set_turret(entity, self.get_component(Body))

class Camera(Component):
    """ A camera, which drawing is done in relation to. """

    def __init__(self, entity, game_services, config):
        """ Initialise the camera. """
        Component.__init__(self, entity, game_services, config)
        self.__position = Vec2d(0, 0)
        self.__screen = game_services.get_screen()
        self.__max_shake = 20
        self.__damping_factor = 10
        self.__shake = 0
        self.__vertical_shake = 0
        self.__horizontal_shake = 0
        self.__tracking = None
        self.__zoom = 0
        self.__zoom_step = 1/2

    def track(self, entity):
        """ Make the camera follow a particular entity. """
        self.__tracking = entity

    def surface(self):
        """ Get the surface drawing will be done on. """
        return self.__screen

    def world_to_screen(self, world):
        """ Convert from world coordinates to screen coordinates. """
        centre = Vec2d(self.__screen.get_size())/2
        return self.zoom_factor * (world - self.position) + centre

    def screen_to_world(self, screen):
        """ Convert from screen coordinates to world coordinates. """
        centre = Vec2d(self.__screen.get_size())/2
        return (screen - centre) / self.zoom_factor + self.position

    def check_bounds_world(self, bbox):
        """ Check whether a world space bounding box is on the screen. """
        if bbox is None: return True
        self_box = self.__screen.get_rect()
        self_box.width /= self.zoom_factor
        self_box.height /= self.zoom_factor
        self_box.center = self.position
        return bbox.colliderect(self_box)

    def check_bounds_screen(self, bbox):
        """ Check whether a screen space bounding box is on the screen. """
        if bbox is None: return True
        return self.__screen.get_rect().colliderect(bbox)

    def update(self, dt):
        """ Update the camera. """

        # If the object we're tracking has been killed then forget about it.
        if self.__tracking is not None and self.__tracking.is_garbage:
            self.__tracking = None

        # Move the camera to track the body. Note that we could do something
        # more complex e.g. interpolate the positions, but this is good enough
        # for now.
        if self.__tracking is not None:
            tracked_body = self.__tracking.get_component(Body)
            if tracked_body is not None:
                self.__position = tracked_body.position

        # Calculate the screen shake effect.
        if self.__shake > 0:
            self.__shake -= dt * self.__damping_factor
        if self.__shake < 0:
            self.__shake = 0
        self.__vertical_shake = (1-2*random.random()) * self.__shake
        self.__horizontal_shake = (1-2*random.random()) * self.__shake

    def apply_shake(self, shake_factor, position):
        """ Apply a screen shake effect. """
        displacement = self.__position - position
        distance = displacement.length
        screen_diagonal = (Vec2d(self.__screen.get_size())/2).length
        max_dist = screen_diagonal * 2
        amount = max(shake_factor * (1.0 - distance/max_dist), 0)
        self.__shake = min(self.__shake+amount, self.__max_shake)

    def play_sound(self, body, sound):
        """ Play a sound at a position. """
        sound = self.game_services.get_resource_loader().load_sound(sound)
        sound.play_positional(body.position - self.__position)

    @property
    def position(self):
        """ Get the position of the camera, adjusted for shake. """
        return self.__position + Vec2d(self.__horizontal_shake,
                                       self.__vertical_shake)

    @position.setter
    def position(self, value):
        """ Set the (actual) position of the camera. """
        self.__position = Vec2d(value)

    @property
    def zoom(self):
        """ Get the zoom level. """
        return self.__zoom

    @zoom.setter
    def zoom(self, value):
        """ Set the zoom level. """
        # zoom can now be negative, not that the if condition made any difference at all before
        # if value > 0:
        self.__zoom = int( value )

    @property
    def zoom_factor(self):
        """ get the multiplier for animation sizes due to zoom """
        return 2 ** ( self.__zoom * self.__zoom_step )

    @property
    def zoom_step(self):
        """ get the zoom adjustment factor """
        return self.__zoom_step
