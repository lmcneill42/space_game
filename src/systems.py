
def towards(e1, e2):
    b1 = e1.get_component(Body)
    b2 = e2.get_component(Body)
    if b1 is None or b2 is None:
        return Vec2d(0, 0)
    return b2.position - b1.position

class FollowsTrackedSystem(ComponentSystem):
    def __init__(self):
        ComponentSystem.__init__(self, [FollowsTracked, Tracking, Body])

    def update(self, dt):
        """ Follows the tracked body. """

        for entity in self.entities():

            # If it's not tracking anything then don't do anything.
            tracked_entity = entity.get_component(Tracking).get_tracked()
            if tracked_entity is None:
                continue

            # Get the pair of bodies.
            this_body = entity.get_component(Body)
            that_body = tracked_entity.get_component(Body)
            assert this_body is not None
            assert that_body is not None

            displacement = that_body.position - this_body.position
            rvel = that_body.velocity - this_body.velocity
            target_dist = self.config["desired_distance_to_player"]

            # distality is a mapping of distance onto the interval [0,1) to
            # interpolate between two behaviours
            distality = 1 - 2 ** ( - displacement.length / target_dist )
            direction = ( 1 - distality ) * rvel.normalized() + distality * displacement.normalized()

            # Determine the fraction of our thrust to apply. This is governed by
            # how far away the target is, and how far away we want to be.
            frac = min(max(displacement.length / target_dist, rvel.length/200), 1)

            # Apply force in the interpolated direction.
            thrust = this_body.mass * self.config["acceleration"]
            force = frac * thrust * direction
            this_body.force = force

class WeaponsSystem(ComponentSystem):

    def __init__(self):
        ComponentSystem.__init(self, [Body, Weapons, Tracking])

    def update(self, dt):
        """ Update the shooting bullet. """

        for entity in self.entities():

            # Get components.
            body = entity.get_component(Body)
            guns = entity.get_component(Weapons)
            tracking = entity.get_component(Tracking)

            # If guns not firing automatically then don't need to do anything.
            if not guns.autofire:
                return

            # Get the selected weapon & the target.
            gun = guns.get_weapon()
            tracked = tracking.get_tracked()
            if gun is None or tracked is None:
                return
            tracked_body = tracked.get_component(Body)

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
                    (hit_body, hit_point, hit_normal) = body.hit_scan()
                    if hit_body == tracked_body:
                        self.can_shoot = False
                        gun.start_shooting_at_body(tracked_body)
            else:
                if self.burst_timer.tick(dt):
                    self.burst_timer.reset()
                    gun.stop_shooting()

class WeaponSystem(ComponentSystem):
    def __init__(self):
        ComponentSystem.__init__(self, [Weapon])

    def update(self, dt):
        """ Create bullets if shooting. Our rate of fire is governed by a timer. """
        for entity in self.entities():
            weapon = entity.get_component(Weapon)
            if weapon.shot_timer > 0:
                weapon.shot_timer -= dt
            if weapon.shooting:
                if weapon.weapon_type == "projectile_thrower":
                    self.shoot_bullet(weapon, dt)
                elif self.weapon_type == "beam":
                    self.shoot_beam(weapon, dt)
                else:
                    # Unknown weapon style.
                    pass

    def shoot_beam(self, weapon, dt):
        """ Shoot a beam. """
        power = weapon.get_power()
        if power is None or not power.consume(weapon.config["power_usage"] * dt):
            weapon.stop_shooting()
        else:
            body = weapon.get_body()
            (hit_body, weapon.impact_point, weapon.impact_normal) = body.hit_scan(
                Vec2d(0, 0),
                Vec2d(0, -1),
                weapon.config["range"],
                weapon.config["radius"]
            )
            if hit_body is not None:
                apply_damage_to_entity(weapon.config["damage"]*dt, hit_body.entity)

    def shoot_bullet(self, weapon, dt):
        """ Shoot a bullet, for projectile thrower type weapons. """

        # If it's time, shoot a bullet and rest the timer. Note that
        # we can shoot more than one bullet in a time step if we have
        # a high enough rate of fire.
        while weapon.shot_timer <= 0:

            # These will be the same for each shot, so get them here...
            body = weapon.get_body()
            shooting_at_dir = weapon.shooting_at.direction()

            # Update the timer.
            weapon.shot_timer += 1.0/self.config["shots_per_second"]

            # Can't spawn bullets if there's nowhere to put them!
            if body is None:
                return

            # Position the bullet somewhere sensible.
            separation = body.size*2
            bullet_position = Vec2d(body.position) + shooting_at_dir * separation

            # Work out the muzzle velocity.
            muzzle_velocity = shooting_at_dir * weapon.config["bullet_speed"]
            spread = weapon.config["spread"]
            muzzle_velocity.rotate_degrees(random.random() * spread - spread)
            bullet_velocity = body.velocity+muzzle_velocity

            # Play a sound.
            shot_sound = weapon.config.get_or_none("shot_sound")
            if shot_sound is not None:
                weapon.entity.game_services.get_camera().play_sound(body, shot_sound)

            # Create the bullet.
            weapon.entity.ecs().create_entity(weapon.config["bullet_config"],
                                              parent=weapon.entity,
                                              team=weapon.__get_team(),
                                              position=bullet_position,
                                              velocity=bullet_velocity,
                                              orientation=shooting_at_dir.normalized().get_angle_degrees()+90)

class TrackingSystem(ComponentSystem):
    """ Track the closest hostile Body."""
    def __init__(self):
        ComponentSystem.__init__(self, [Tracking, Body])
    def update(self, dt):
        for entity in self.entities():
            self_body = entity.get_component(Body)
            tracking = entity.get_component(Tracking)
            if tracking.tracked.entity is None:
                self_team = entity.get_component(Team) # optional
                def f(body):
                    team = body.entity.get_component(Team)
                    if self_team is None or team is None:
                        return False
                    return not team.on_same_team(self_team)
                closest = self.entity.ecs().get_system(Physics).closest_body_with(
                    self_body.position,
                    f
                )
                if closest:
                    tracking.tracked.entity = closest.entity

class LaunchesFightersSystem(ComponentSystem):
    def __init__(self):
        ComponentSystem.__init__(self, [LaunchesFighers, Body, Tracking, Team])
    def update(self, dt):
        for entity in self.entities():
            launcher = entity.get_component(LaunchesFighters)
            body = entity.get_component(Body)
            tracking = entity.get_component(Tracking)
            team = entity.get_component(Team)
            if self.spawn_timer.tick(dt):
                self.spawn_timer.reset()
                for i in range(self.config["num_fighters"]):
                    direction = towards(entity, tracking.tracked.entity)
                    spread = launcher.config["takeoff_spread"]
                    direction.rotate_degrees(spread*random.random()-spread/2.0)
                    child = entity.ecs().create_entity(
                        launcher.config["fighter_config"],
                        team=team.get_team(),
                        position=body.position,
                        velocity=body.velocity + direction * launcher.config["takeoff_speed"]
                    )


def apply_damage_to_entity(damage, entity):
    """ Apply damage to an object we've hit. """
    shields = entity.get_component(Shields)
    if shields is None:
        ancestor = entity.get_ancestor_with_component(Shields)
        if ancestor is not None:
            shields = ancestor.get_component(Shields)
    if shields is not None:
        shields.hp -= damage
        if shields.hp < 0:
            damage = -shields.hp
        else:
            damage = 0
    hitpoints = entity.get_component(Hitpoints)
    if hitpoints is not None:
        hitpoints.receive_damage(damage)
        hitpoints.hp -= amount
        if hitpoints.hp <= 0:
            entity.kill()

class KillOnTimerSystem(ComponentSystem):
    def __init__(self):
        pass
    def update(self, dt):
        if self.lifetime.tick(dt):
            self.entity.kill()

class ExplodesOnDeathSystem(ComponentSystem):
    def __init__(self):
        pass
    def on_object_killed(self):
        body = self.entity.get_component(Body)
        explosion = self.entity.ecs().create_entity(self.config["explosion_config"],
                                            position=body.position,
                                            velocity=body.velocity)
        shake_factor = self.config.get_or_default("shake_factor", 1)
        camera = self.entity.game_services.get_camera()
        camera.apply_shake(shake_factor, body.position)

        # Play a sound.
        sound = self.config.get_or_none("sound")
        if sound is not None:
            camera.play_sound(body, sound)


class EndProgramOnDeathSystem(ComponentSystem):
    def __init__(self):
        pass
    def on_object_killed(self):
        self.entity.game_services.end_game()


class PowerSystem(ComponentSystem):
    def update(self, dt):
        if self.overloaded:
            if self.overload_timer.tick(dt):
                self.overloaded = False
                self.overload_timer.reset()
        else:
            self.power = min(self.capacity, self.power + self.recharge_rate * dt)

class ShieldSystem(ComponentSystem):

    def update(self, dt):
        power = self.entity.get_component(Power)
        if power is None:
            self.hp = 0
        else:
            if self.overloaded:
                if self.overload_timer.tick(dt):
                    self.overloaded = False
                    self.overload_timer.reset()
            else:
                recharge_amount = min(self.max_hp - self.hp, self.recharge_rate * dt)
                self.hp = min(self.max_hp, self.hp + power.consume(recharge_amount))

class TextSystem(ComponentSystem):
    def update(self, dt):
        if self.blink():
            if self.__blink_timer.tick(dt):
                self.__blink_timer.reset()
                self.__visible = not self.__visible
        if self.__warning is not None:
            self.__offs += self.__scroll_speed * dt
            self.__offs = self.__offs % (self.__warning.get_width()+self.__padding)

class AnimSystem(ComponentSystem):
    def update(self, dt):
        if self.__anim.tick(dt):
            if self.config.get_or_default("kill_on_finish", 0):
                self.entity.kill()
            else:
                self.__anim.reset()

class ThrusterSystem(ComponentSystem):
    def __init__(self):
        ComponentSystem.__init__(self, [Thruster])
    def update(self, dt):
        for entity in self.entities():
            thruster = entity.get_component(Thruster)
            attached = thruster.attached_to.entity
            if attached is None:
                entity.kill()
            else:
                body = attached.get_component(Body)
                body.apply_force(...)

class ThrustersSystem(ComponentSystem):
    def __init__(self):
        ComponentSystem.__init__(self, [Body, Thrusters])
    def update(self, dt):
        for entity in self.entities():
            body = entity.get_component(Body)
            thrusters = entity.get_component(Thrusters)
            turn = thrusters.turn
            if turn == 0 and self.__direction.x == 0:
                eps = 10 # LOLOLOL
                if body.angular_velocity > eps:
                    turn = -1
                elif body.angular_velocity < -eps:
                    turn = 1
            body.fire_correct_thrusters(thrusters.direction, turn)

class WaveSpawnerSystem(ComponentSystem):
    """ Spawns waves of enemies. """

    def __init__(self):
        ComponentSystem.__init__(self, [])
        self.wave = 1
        self.spawned = []
        self.message = None
        self.done = False

    def update(self, dt):
        """ Update the spawner. """

        # Check for end condition and show game ending message if so.
        if self.done:
            return
        elif self.player_is_dead() or self.max_waves():
            self.done = True
            txt = "GAME OVER"
            if self.max_waves():
                txt = "VICTORY"
            message = self.game_services.get_entity_manager().create_entity("endgame_message.txt", text=txt)

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
            self.spawned.append(
                self.game_services.get_entity_manager().create_entity(
                    enemy_type,
                    position=enemy_position,
                    team="enemy"
                )
            )

    def wave_is_dead(self):
        """ Has the last wave been wiped out? """
        self.spawned = list( filter(lambda x: not x.is_garbage, self.spawned) )
        return len(self.spawned) == 0

    def prepare_for_wave(self):
        """ Prepare for a wave. """
        self.message = self.game_services.entity_manager().create_entity(
            "update_message.txt",
            text="WAVE %s PREPARING" % self.wave
        )

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

class CameraSystem(object):

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

