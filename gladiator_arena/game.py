# ============================================================
#  GLADIATOR ARENA - Game State Controller
# ============================================================
import pygame, math, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import *
from src.ui import (draw_panel, draw_text, Button, HUD,
                     ArenaBackground, FloatingTextManager, ScreenEffects, get_font,
                     draw_tooltip, load_icon)
from src.player import Player
from src.enemy import Enemy
from src.combat import Combat, _get_player_skill
from src.shop import Shop
from src.arena import Arena
from src.particle_system import particles
from src.save_system import SaveSystem
from src.sound_manager import sounds
from src.animation import anim_manager
from src.items import Equipment, Item, Inventory


# ── State IDs ────────────────────────────────────────────────
ST_MENU    = 'menu'
ST_CHARGEN = 'chargen'
ST_ARENA   = 'arena'
ST_COMBAT  = 'combat'
ST_SHOP    = 'shop'
ST_GAMEOVER= 'gameover'
ST_VICTORY = 'victory'
ST_CAMPFIRE= 'campfire'  # Between-fight hub
ST_OVERLORD= 'overlord'
ST_INV     = 'inventory'
ST_OPTIONS = 'options'

OVERLORDS = [
    {
        'level': 1, 'title': 'The Ashen Tyrant',
        'portrait': 'overlord1',
        'hp': 1400, 'damage': 70, 'defense': 28,
        'required_rank': 6,
        'intro': 'Molten wrath erupts as the Ashen Tyrant steps from the ashes.',
        'drops': [
            {'category': 'Chestplates', 'items': ['Titanlord’s Dominion', 'Eternal Sovereign Plate']},
            {'category': 'Rings', 'items': ['Ring of the Void Emperor', 'Omega Ring of Eternity']},
        ],
    },
    {
        'level': 2, 'title': 'The Skull Crusher',
        'portrait': 'overlord2',
        'hp': 1900, 'damage': 90, 'defense': 36,
        'required_rank': 0,
        'intro': 'Bones splinter beneath the Skull Crusher before the battle even begins.',
        'drops': [
            {'category': 'Helmets', 'items': ['Astral Warden Mask', 'Voidseer Visage']},
            {'category': 'Necklaces', 'items': ['Amulet of the Ninth Realm', 'The Cosmic Sigil']},
        ],
    },
    {
        'level': 3, 'title': 'The Abyss Walker',
        'portrait': 'overlord3',
        'hp': 2500, 'damage': 110, 'defense': 46,
        'required_rank': 0,
        'intro': 'The Abyss walker drags shadowed terror into the arena with every step.',
        'drops': [
            {'category': 'Pants', 'items': ['Netherwoven Legguards', 'Greaves of the Eternal Throne']},
            {'category': 'Boots', 'items': ['Voidstride Treads', 'Celestial Phantom Steps']},
        ],
    },
    {
        'level': 4, 'title': 'The Blood Emperor',
        'portrait': 'overlord4',
        'hp': 3300, 'damage': 135, 'defense': 56,
        'required_rank': 0,
        'intro': 'A crimson crown descends as the Blood Emperor claims the arena.',
        'drops': [
            {'category': 'Shields', 'items': ['Shield of Celestial Judgment', 'Aegis of the Void Star']},
        ],
    },
    {
        'level': 5, 'title': 'The World Ender',
        'portrait': 'overlord5',
        'hp': 4400, 'damage': 165, 'defense': 70,
        'required_rank': 0,
        'intro': 'The final apocalypse approaches with the World Ender’s arrival.',
        'drops': [
            {'category': 'Weapons', 'items': ['The Godslayer’s Oath', 'Worldrend, Blade of the Last Dawn']},
        ],
    },
]


class Game:
    def __init__(self, screen):
        self.screen  = screen
        self.render_surface = pygame.Surface((SCREEN_W, SCREEN_H))
        self.screen_mode = 'default'  # 'default' or 'fullscreen'
        self.clock   = pygame.time.Clock()
        self.state   = ST_MENU
        self.running = True
        self.dt      = 0.0

        # Core objects
        self.player     = None
        self.enemy      = None
        self.arena_bg   = ArenaBackground(SCREEN_W, SCREEN_H)
        self.hud        = HUD(SCREEN_W, SCREEN_H)
        self.effects    = ScreenEffects()
        self.shop       = None  # Persistent shop instance
        self.arena_sys  = Arena(SCREEN_W, SCREEN_H)
        self.assets     = {}
        self.bg_assets  = {}
        self.campfire_hidden = False
        self.combat_arena_tier = 0
        self._load_assets()

        # Combat state
        self.combat_phase   = 'player_turn'  # player_turn | enemy_turn | result | anim
        self.combat_result  = None
        self.combat_msg     = ''
        self.combat_msg_timer= 0.0
        self.turn_number    = 0
        self.heavy_cooldown = 0
        self.combat_buttons = []
        self.potion_slot_rects = []
        self.anim_timer     = 0.0
        self.enemy_anim_state = 'idle'
        self.overlord_cards = []
        self.overlord_back_btn = None
        self.overlord_scroll_y = 0
        self.overlord_max_scroll = 0
        self.overlord_menu_t = 0.0
        self.overlord_mode = False
        self.overlord_level = 0
        self.overlord_card_hover = None
        self.overlord_msg = ''
        self.overlord_msg_t = 0.0
        self.in_overlord_fight = False
        self.current_overlord_level = 0
        # one-time processing flags to avoid repeated handling
        self._victory_processed = False
        self._gameover_processed = False

        # Menu
        self._build_menu()

        # Load sounds
        sounds.load()
        self._ensure_music()

    # ── State machine ─────────────────────────────────────────

    def run(self):
        while self.running:
            try:
                raw_dt = self.clock.tick(FPS) / 1000.0
                effect_dt = min(raw_dt, 0.1)
                self.effects.update(effect_dt)
                self.dt = min(raw_dt * self.effects.time_scale, 0.1)

                if self.effects.frozen:
                    self.dt = 0.0

                events = pygame.event.get()
                for event in events:
                    try:
                        if event.type == pygame.QUIT:
                            self.running = False
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                self._on_escape()
                        self._handle_event(event)
                    except Exception:
                        self._log_exception('Event handler error')

                try:
                    self._update()
                except Exception:
                    self._log_exception('Update error')

                self._ensure_music()

                try:
                    self._draw()
                except Exception:
                    self._log_exception('Draw error')

                try:
                    pygame.display.flip()
                except Exception:
                    self._log_exception('Display flip error')

            except Exception:
                self._log_exception('Main loop error')
                # stop running to avoid endless exception loops
                self.running = False

        pygame.quit()

    def _log_exception(self, context=''):
        import traceback
        tb = traceback.format_exc()
        msg = f"[{context}]\n{tb}\n"
        print(msg)
        try:
            with open('error.log', 'a', encoding='utf-8') as f:
                f.write(msg)
        except Exception:
            pass

    def _ensure_music(self):
        if self.state == ST_COMBAT:
            sounds.play_music('fight_arena')
        else:
            sounds.play_music('background')

    def _on_escape(self):
        if self.state in (ST_SHOP, ST_INV, ST_OPTIONS):
            self.state = ST_CAMPFIRE
        elif self.state == ST_ARENA:
            self.state = ST_CAMPFIRE
        elif self.state == ST_OVERLORD:
            self.state = ST_CAMPFIRE
        elif self.state == ST_CAMPFIRE:
            self.state = ST_MENU
        elif self.state == ST_CHARGEN:
            self.state = ST_MENU

    def _fix_mouse_pos(self, pos):
        if pos is None:
            return pos
        x, y = pos
        if self.screen_mode == 'fullscreen':
            disp_w, disp_h = self.screen.get_size()
            if disp_w and disp_h:
                x = x * SCREEN_W / disp_w
                y = y * SCREEN_H / disp_h
        ox = int(self.effects.shake_x)
        oy = int(self.effects.shake_y)
        return (int(x - ox), int(y - oy))

    def _handle_event(self, event):
        if hasattr(event, 'pos'):
            event.pos = self._fix_mouse_pos(event.pos)

        if self.state == ST_MENU:
            self._handle_menu(event)
        elif self.state == ST_CHARGEN:
            self._handle_chargen(event)
        elif self.state == ST_CAMPFIRE:
            self._handle_campfire(event)
        elif self.state == ST_OVERLORD:
            self._handle_overlord(event)
        elif self.state == ST_COMBAT:
            self._handle_combat(event)
        elif self.state == ST_ARENA:
            action = self.arena_sys.handle_event(event)
            if action == 'back':
                sounds.play('button_click')
                self.state = ST_CAMPFIRE
            elif action == 'fight':
                sounds.play('button_click')
                self._start_fight()
        elif self.state == ST_SHOP:
            res = self.shop.handle_event(event, self.player)
            if res == 'close':
                sounds.play('button_click')
                self.state = ST_CAMPFIRE
        elif self.state == ST_INV:
            self._handle_inventory(event)
        elif self.state == ST_GAMEOVER:
            for btn in self._gameover_btns:
                if btn.is_clicked(event):
                    sounds.play('button_click')
                    if btn.text == 'MENU':
                        self.state = ST_MENU
                    elif btn.text == 'RETRY':
                        # Restart from save (load persisted state, preserving the loss count)
                        self._restart_from_save()
        elif self.state == ST_VICTORY:
            for btn in self._victory_btns:
                if btn.is_clicked(event):
                    sounds.play('button_click')
                    if btn.text == 'CONTINUE':
                        self.state = ST_CAMPFIRE
                    elif btn.text == 'ARENA':
                        self.state = ST_ARENA
                    elif btn.text == 'CAMP':
                        self.state = ST_CAMPFIRE
        elif self.state == ST_OPTIONS:
            self._handle_options(event)

    def _update(self):
        dt = self.dt
        ms = self._fix_mouse_pos(pygame.mouse.get_pos())
        
        if self.state == ST_MENU:
            self._update_menu(dt, ms)
        elif self.state == ST_CHARGEN:
            self._update_chargen(dt, ms)
        elif self.state == ST_CAMPFIRE:
            self._update_campfire(dt, ms)
        elif self.state == ST_OVERLORD:
            self._update_overlord(dt, ms)
        elif self.state == ST_COMBAT:
            if self.enemy and not self.enemy.alive:
                self._on_enemy_death()
            else:
                self._update_combat(dt, ms)
        elif self.state == ST_ARENA:
            self.arena_sys.update(dt, ms)
        elif self.state == ST_SHOP:
            self.shop.update(dt, ms, self.player)
        elif self.state == ST_INV:
            self._update_inventory(dt, ms)
        elif self.state == ST_GAMEOVER:
            for btn in self._gameover_btns:
                btn.update(dt, ms)
        elif self.state == ST_VICTORY:
            for btn in self._victory_btns:
                btn.update(dt, ms)
        elif self.state == ST_OPTIONS:
            self._update_options(dt, ms)

        if self.hud:
            self.hud.update(dt)

        # Update particles and effects
        particles.update(dt)
        self.effects.update(dt)
        anim_manager.update(dt)

        # Player renderer
        if self.player:
            self.player.renderer.update(dt)
        if self.enemy:
            self.enemy.renderer.update(dt)

    def _draw(self):
        ox = int(self.effects.shake_x)
        oy = int(self.effects.shake_y)
        # Create offset surface
        surf = self.render_surface
        surf.fill((0, 0, 0))

        if self.state == ST_CAMPFIRE:
            bg = self.bg_assets.get('Menu_background.png')
            if bg:
                self._draw_background(surf, bg)
            else:
                self.arena_bg.draw(surf)
        else:
            self.arena_bg.draw(surf)
        particles.draw(surf)

        if self.state == ST_MENU:
            self._draw_menu(surf)
        elif self.state == ST_CHARGEN:
            self._draw_chargen(surf)
        elif self.state == ST_CAMPFIRE:
            self._draw_campfire(surf)
        elif self.state == ST_OVERLORD:
            self._draw_overlord(surf)
        elif self.state == ST_COMBAT:
            self._draw_combat(surf)
        elif self.state == ST_ARENA:
            tier = self.arena_sys.get_current_tier(self.player) if self.player else 0
            bg = self._get_arena_tier_background(tier)
            self.arena_sys.draw(surf, self.player, bg)
        elif self.state == ST_SHOP:
            self.arena_bg.draw(surf)
            ms = self._fix_mouse_pos(pygame.mouse.get_pos())
            self.shop.draw(surf, self.player, ms)
        elif self.state == ST_INV:
            self._draw_inventory(surf)
        elif self.state == ST_GAMEOVER:
            self._draw_gameover(surf)
        elif self.state == ST_VICTORY:
            self._draw_victory(surf)
        elif self.state == ST_OPTIONS:
            self._draw_options(surf)

        self.effects.draw_overlay(surf)
        if self.screen_mode == 'fullscreen':
            display_size = self.screen.get_size()
            scaled = pygame.transform.smoothscale(surf, display_size)
            self.screen.blit(scaled, (0, 0))
        else:
            self.screen.blit(surf, (ox, oy))

    # ═══════════════════════════════════════════════════════════
    #  MAIN MENU
    # ═══════════════════════════════════════════════════════════

    def _build_menu(self):
        cx = SCREEN_W // 2
        by = SCREEN_H // 2 - 50
        self.menu_buttons = [
            Button(cx-120, by,      240, 50, 'NEW GAME', 24),
            Button(cx-120, by+65,   240, 50, 'CONTINUE', 24),
            Button(cx-120, by+130,  240, 50, 'OPTIONS',  24),
            Button(cx-120, by+195,  240, 50, 'EXIT',     24,
                   color=(80,30,30), hover_color=(160,50,50)),
        ]
        if not SaveSystem.has_save():
            self.menu_buttons[1].enabled = False
        self.menu_t = 0.0
        self.menu_title_y = -80.0
        self.menu_title_tween = None

    def _update_menu(self, dt, ms):
        self.menu_t += dt
        for btn in self.menu_buttons:
            btn.update(dt, ms)
        if self.menu_title_y < 60:
            self.menu_title_y += dt * 180

    def _load_assets(self):
        base = os.path.join(os.path.dirname(__file__), 'assets')
        for name in ('fight.png', 'shop.png', 'Inventory.png', 'arena_ranks.png', 'save.png', 'menu.png'):
            path = os.path.join(base, name)
            try:
                img = pygame.image.load(path).convert_alpha()
            except Exception:
                img = None
            self.assets[name] = img

        for name in ('Menu_background.png', 'The_pit.png', 'Sand_and_Blood.png',
                     'Iron_Colosseum.png', 'Golden_Colosseum.png'):
            path = os.path.join(base, name)
            try:
                img = pygame.image.load(path).convert_alpha()
            except Exception:
                img = None
            self.bg_assets[name] = img

    def _set_screen_mode(self, mode):
        if mode == 'fullscreen':
            self.screen_mode = 'fullscreen'
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen_mode = 'default'
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.render_surface = pygame.Surface((SCREEN_W, SCREEN_H))

    def _get_arena_tier_background(self, tier_index):
        tier_bgs = [
            'The_pit.png',
            'Sand_and_Blood.png',
            'Iron_Colosseum.png',
            'Golden_Colosseum.png',
        ]
        if 0 <= tier_index < len(tier_bgs):
            return self.bg_assets.get(tier_bgs[tier_index])
        return None

    def _draw_background(self, surface, bg_image):
        if not bg_image:
            return
        if bg_image.get_size() != (SCREEN_W, SCREEN_H):
            bg_image = pygame.transform.smoothscale(bg_image, (SCREEN_W, SCREEN_H))
        surface.blit(bg_image, (0, 0))

    def _handle_menu(self, event):
        for btn in self.menu_buttons:
            if btn.is_clicked(event):
                sounds.play('button_click')
                if btn.text == 'NEW GAME':
                    self._start_chargen()
                elif btn.text == 'CONTINUE':
                    self._load_game()
                elif btn.text == 'OPTIONS':
                    self._open_options()
                elif btn.text == 'EXIT':
                    self.running = False

    def _draw_menu(self, surface):
        bg = self.bg_assets.get('Menu_background.png')
        if bg:
            self._draw_background(surface, bg)

        t = self.menu_t

        # Animated title
        ty = int(self.menu_title_y)
        title_pulse = math.sin(t*1.8)*4

        # Title backdrop
        tw, th = 700, 90
        tx = SCREEN_W//2 - tw//2
        draw_panel(surface, pygame.Rect(tx, ty-5, tw, th+10), color=BRONZE_DK, border=GOLD)

        # Main title
        draw_text(surface, 'GLADIATOR ARENA', SCREEN_W//2, ty+8,
                  52, GOLD, bold=True, center=True)
        draw_text(surface, '— Swords & Sandals —', SCREEN_W//2, ty+58,
                  20, PARCHMENT, center=True)

        # Subtitle tagline
        draw_text(surface, 'Rise. Fight. Conquer.',
                  SCREEN_W//2, ty + 100, 22, (200,180,120), center=True)

        # Draw animated gladiator silhouette
        self._draw_menu_gladiator(surface, t)

        # Buttons
        for btn in self.menu_buttons:
            btn.draw(surface)

        # Version
        draw_text(surface, 'v1.0  |  Python Edition',
                  SCREEN_W - 10, SCREEN_H - 24, 14, GRAY)

    def _draw_menu_gladiator(self, surface, t):
        """Animated hero pose on menu screen."""
        from src.player import GladiatorRenderer
        # Left gladiator
        r1 = GladiatorRenderer(SCREEN_W//2 - 260, SCREEN_H//2 + 50,
                                facing=1, scale=1.0,
                                skin=(200,160,100), armor_color=(140,60,40))
        r1.anim_timer = t
        r1.bob = math.sin(t*1.8)*4
        r1.arm_raise = 0.2 + math.sin(t*2)*0.1
        r1.weapon_angle = -10 + math.sin(t*1.5)*8
        r1.draw(surface)
        # Right gladiator
        r2 = GladiatorRenderer(SCREEN_W//2 + 260, SCREEN_H//2 + 50,
                                facing=-1, scale=1.0,
                                skin=(190,145,85), armor_color=(60,80,160))
        r2.anim_timer = t + 0.7
        r2.bob = math.sin((t+0.7)*1.8)*4
        r2.arm_raise = 0.15 + math.sin((t+0.7)*2)*0.1
        r2.weapon_angle = -15 + math.sin((t+0.7)*1.5)*8
        r2.draw(surface)

    # ═══════════════════════════════════════════════════════════
    #  CHARACTER CREATION
    # ═══════════════════════════════════════════════════════════

    def _start_chargen(self):
        self.state = ST_CHARGEN
        self.cg_name   = 'Maximus'
        self.cg_class  = 0
        self.cg_skin   = 0
        self.cg_armor  = 0
        self.cg_t      = 0.0
        self.cg_typing = False
        self._build_chargen_buttons()
        self.cg_preview_renderer = None
        self._update_chargen_preview()

    SKIN_TONES = [
        (235,195,140), (210,170,120), (190,148,95),
        (160,120,70),  (120,80,40),   (90,55,20),
    ]
    ARMOR_COLORS = [
        (160,60,40), (60,80,180), (40,130,60),
        (130,100,20),(80,40,120), (40,80,100),
    ]
    CLASS_NAMES = list(CLASSES.keys())

    def _build_chargen_buttons(self):
        cx = SCREEN_W//2
        self.cg_btns = {
            'class_prev': Button(cx-200, 310, 44, 36, '<', 22),
            'class_next': Button(cx+160, 310, 44, 36, '>', 22),
            'skin_prev':  Button(cx-200, 370, 44, 36, '<', 22),
            'skin_next':  Button(cx+160, 370, 44, 36, '>', 22),
            'armor_prev': Button(cx-200, 430, 44, 36, '<', 22),
            'armor_next': Button(cx+160, 430, 44, 36, '>', 22),
            'start':      Button(cx-110, 570, 220, 52, 'ENTER ARENA!', 24,
                                  color=(140,30,30), hover_color=(220,50,50)),
            'back':       Button(20, SCREEN_H-70, 130, 44, 'BACK', 20,
                                  color=BRONZE_DK, hover_color=BRONZE),
        }

    def _update_chargen_preview(self):
        skin = self.SKIN_TONES[self.cg_skin % len(self.SKIN_TONES)]
        armor= self.ARMOR_COLORS[self.cg_armor % len(self.ARMOR_COLORS)]
        cls  = self.CLASS_NAMES[self.cg_class % len(self.CLASS_NAMES)]
        wpn  = CLASSES[cls]['weapon']
        from src.player import GladiatorRenderer
        self.cg_preview_renderer = GladiatorRenderer(
            SCREEN_W//2 + 230, SCREEN_H//2 - 20,
            facing=-1, scale=1.4, skin=skin, armor_color=armor,
            weapon_name=wpn, class_name=cls)

    def _update_chargen(self, dt, ms):
        self.cg_t += dt
        for btn in self.cg_btns.values():
            btn.update(dt, ms)
        if self.cg_preview_renderer:
            self.cg_preview_renderer.anim_timer = self.cg_t
            self.cg_preview_renderer.bob = math.sin(self.cg_t*1.8)*4
            self.cg_preview_renderer.arm_raise = 0.1 + math.sin(self.cg_t*2)*0.05

    def _handle_chargen(self, event):
        btns = self.cg_btns
        sounds_played = False
        def click(b): return btns[b].is_clicked(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE and self.cg_typing:
                self.cg_name = self.cg_name[:-1]
            elif event.key == pygame.K_RETURN:
                self.cg_typing = False
            elif self.cg_typing and len(self.cg_name) < 16:
                if event.unicode.isprintable():
                    self.cg_name += event.unicode
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Click on name field to edit
            name_r = pygame.Rect(SCREEN_W//2-120, 248, 240, 36)
            if name_r.collidepoint(event.pos):
                self.cg_typing = True

        for key, btn in btns.items():
            if btn.is_clicked(event):
                sounds.play('button_click')
                if key == 'class_prev':  self.cg_class  -= 1; self._update_chargen_preview()
                elif key == 'class_next':self.cg_class  += 1; self._update_chargen_preview()
                elif key == 'skin_prev': self.cg_skin   -= 1; self._update_chargen_preview()
                elif key == 'skin_next': self.cg_skin   += 1; self._update_chargen_preview()
                elif key == 'armor_prev':self.cg_armor  -= 1; self._update_chargen_preview()
                elif key == 'armor_next':self.cg_armor  += 1; self._update_chargen_preview()
                elif key == 'start': self._create_player()
                elif key == 'back':  self.state = ST_MENU

    def _create_player(self):
        name  = self.cg_name.strip() or 'Maximus'
        cls   = self.CLASS_NAMES[self.cg_class % len(self.CLASS_NAMES)]
        skin  = self.SKIN_TONES[self.cg_skin % len(self.SKIN_TONES)]
        armor = self.ARMOR_COLORS[self.cg_armor % len(self.ARMOR_COLORS)]
        self.player = Player(name=name, class_name=cls, skin=skin,
                              armor_color=armor)
        # Give starter potions
        from src.items import Item
        self.player.inventory.add(Item('Health Potion'))
        self.player.inventory.add(Item('Health Potion'))
        # Create a new shop instance for this playthrough
        self.shop = Shop(SCREEN_W, SCREEN_H)
        self.state = ST_CAMPFIRE
        self._build_campfire()
        SaveSystem.save(self.player, shop_data=self.shop.to_dict())

    def _draw_chargen(self, surface):
        # Dark overlay
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0,0,0,140))
        surface.blit(overlay, (0,0))

        pw, ph = 550, 500
        cx = SCREEN_W//2
        panel_r = pygame.Rect(cx-pw//2, 100, pw, ph)
        draw_panel(surface, panel_r, color=STONE, border=GOLD)

        draw_text(surface, 'CREATE YOUR GLADIATOR', cx, panel_r.y+14,
                  30, GOLD, bold=True, center=True)

        # Name input
        draw_text(surface, 'Gladiator Name:', cx-120, 222, 17, PARCHMENT)
        name_r = pygame.Rect(cx-120, 248, 240, 36)
        col = GOLD if self.cg_typing else BRONZE
        pygame.draw.rect(surface, DARK_GRAY, name_r, border_radius=5)
        pygame.draw.rect(surface, col, name_r, 2, border_radius=5)
        cursor = '|' if self.cg_typing and int(self.cg_t*2) % 2 == 0 else ''
        draw_text(surface, self.cg_name + cursor, name_r.x+8, name_r.y+6,
                  20, WHITE, shadow=False)

        # Class selector
        cls = self.CLASS_NAMES[self.cg_class % len(self.CLASS_NAMES)]
        cls_data = CLASSES[cls]
        draw_text(surface, 'Class:', cx-120, 292, 17, PARCHMENT)
        draw_text(surface, cls, cx-10, 292, 20, GOLD, bold=True, center=True)
        draw_text(surface, cls_data['desc'], cx, 315, 13, STONE_LT, center=True)

        # Skin tone
        skin_i = self.cg_skin % len(self.SKIN_TONES)
        draw_text(surface, 'Skin Tone:', cx-120, 352, 17, PARCHMENT)
        sc = self.SKIN_TONES[skin_i]
        pygame.draw.circle(surface, sc, (cx, 362), 14)
        pygame.draw.circle(surface, GOLD, (cx, 362), 14, 2)

        # Armor color
        ac_i = self.cg_armor % len(self.ARMOR_COLORS)
        draw_text(surface, 'Armor Color:', cx-120, 412, 17, PARCHMENT)
        ac = self.ARMOR_COLORS[ac_i]
        pygame.draw.rect(surface, ac, (cx-16, 406, 32, 18), border_radius=4)
        pygame.draw.rect(surface, GOLD, (cx-16, 406, 32, 18), 2, border_radius=4)

        # Stats preview
        stat_x = panel_r.x + 16
        sy2 = 292
        for stat, val in [('STR', cls_data['strength']), ('DEF', cls_data['defense']),
                           ('AGI', cls_data['agility']),  ('INT', cls_data['intelligence']),
                           ('CRIT', cls_data['crit']),    ('HP', cls_data['hp'])]:
            draw_text(surface, f'{stat}: {val}',
                      panel_r.right - 100, sy2, 14, PARCHMENT, shadow=False)
            sy2 += 18

        # Preview character
        if self.cg_preview_renderer:
            self.cg_preview_renderer.draw(surface)

        # Buttons
        for btn in self.cg_btns.values():
            btn.draw(surface)

    # ═══════════════════════════════════════════════════════════
    #  CAMPFIRE HUB (between fights)
    # ═══════════════════════════════════════════════════════════

    def _build_campfire(self):
        self.campfire_hidden = False
        # Build campfire buttons sized to fit the campfire panel exactly
        pw, ph = 520, 560
        pr = pygame.Rect(SCREEN_W//2 - pw//2, SCREEN_H//2 - ph//2 - 40, pw, ph)
        header_h = 112
        margin_x = 32
        button_w = pr.width - (margin_x * 2)
        button_h = 56
        gap = 14
        # start inside the panel just below the header
        start_y = pr.y + header_h + 16
        bx = pr.x + margin_x
        self.cf_buttons = [
            Button(bx, start_y + (button_h+gap)*0, button_w, button_h, 'FIGHT!', 26,
                   color=(180, 40, 40), hover_color=(240, 70, 70),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('fight.png'), icon_size=(28,28)),
            Button(bx, start_y + (button_h+gap)*1, button_w, button_h, 'SHOP', 24,
                   color=(160, 110, 35), hover_color=(220, 170, 70),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('shop.png'), icon_size=(28,28)),
            Button(bx, start_y + (button_h+gap)*2, button_w, button_h, 'INVENTORY', 24,
                   color=(40, 120, 80), hover_color=(80, 190, 120),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('Inventory.png'), icon_size=(28,28)),
            Button(bx, start_y + (button_h+gap)*3, button_w, button_h, 'OVERLORD', 22,
                   color=(35, 70, 150), hover_color=(90, 140, 230),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('arena_ranks.png'), icon_size=(28,28)),
            Button(bx, start_y + (button_h+gap)*4, button_w, button_h, 'SAVE', 22,
                   color=(100, 70, 140), hover_color=(150, 110, 200),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('save.png'), icon_size=(28,28)),
            Button(bx, start_y + (button_h+gap)*5, button_w, button_h, 'MENU', 22,
                   color=(60, 60, 60), hover_color=(110, 110, 110),
                   text_color=WHITE, border_color=GOLD,
                   icon=self.assets.get('menu.png'), icon_size=(28,28)),
        ]
        self.cf_t = 0.0
        self.cf_msg = ''
        self.cf_msg_t = 0.0

    def _update_campfire(self, dt, ms):
        self.cf_t += dt
        if hasattr(self, 'cf_buttons'):
            for btn in self.cf_buttons:
                btn.update(dt, ms)
        if self.cf_msg_t > 0:
            self.cf_msg_t -= dt
        else:
            self.cf_msg = ''

    def _build_overlord_menu(self):
        pw, ph = 1150, 760
        pr = pygame.Rect((SCREEN_W - pw) // 2, (SCREEN_H - ph) // 2, pw, ph)
        self.overlord_panel = pr
        self.overlord_cards = []

        self.overlord_scroll_y = 0
        self.overlord_max_scroll = 0
        self.overlord_msg = ''
        self.overlord_msg_t = 0.0

        header_h = 146
        footer_h = 106
        content_top = pr.y + header_h + 18
        content_height = pr.height - header_h - footer_h - 32
        content_left = pr.x + 24
        content_width = pr.width - 48
        card_h = 240
        card_gap = 22

        for idx, meta in enumerate(OVERLORDS):
            base_y = content_top + idx * (card_h + card_gap)
            card_rect = pygame.Rect(content_left, base_y, content_width, card_h)
            fight_btn = Button(card_rect.right - 168, base_y + card_h // 2 - 28,
                               150, 56, 'FIGHT', 20,
                               color=(170, 18, 18), hover_color=(240, 44, 44),
                               text_color=WHITE, border_color=GOLD)
            fight_btn.base_x = fight_btn.rect.x
            fight_btn.base_y = fight_btn.rect.y
            self.overlord_cards.append({
                'meta': meta,
                'rect': card_rect,
                'base_y': base_y,
                'fight_btn': fight_btn,
            })

        self.overlord_back_btn = Button(pr.x + 26, pr.bottom - 72,
                                       180, 52, 'BACK', 20,
                                       color=(70, 70, 70), hover_color=(120, 120, 120),
                                       text_color=WHITE, border_color=GOLD)

    def _update_overlord(self, dt, ms):
        for card in self.overlord_cards:
            card['rect'].y = card['base_y'] - self.overlord_scroll_y
            card['fight_btn'].rect.y = card['fight_btn'].base_y - self.overlord_scroll_y
            card['fight_btn'].update(dt, ms)
            meta = card['meta']
            locked = ((meta['level'] == 1 and self.player.arena_rank < meta['required_rank']) or
                      (meta['level'] > 1 and self.player.overlord_unlocked < meta['level']))
            if locked:
                card['fight_btn'].enabled = False
                card['fight_btn'].color = (50, 20, 28)
                card['fight_btn'].hover_color = (50, 20, 28)
                card['fight_btn'].text_color = STONE_LT
                card['fight_btn'].border_color = STONE_LT
            else:
                card['fight_btn'].enabled = True
                card['fight_btn'].color = (170, 18, 18)
                card['fight_btn'].hover_color = (240, 44, 44)
                card['fight_btn'].text_color = WHITE
                card['fight_btn'].border_color = GOLD

        if self.overlord_back_btn:
            self.overlord_back_btn.update(dt, ms)

        if self.overlord_msg_t > 0:
            self.overlord_msg_t -= dt
        else:
            self.overlord_msg = ''

    def _handle_overlord(self, event):
        if self.overlord_back_btn and self.overlord_back_btn.is_clicked(event):
            sounds.play('button_click')
            self.state = ST_CAMPFIRE
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:
                self.overlord_scroll_y = max(0, self.overlord_scroll_y - 80)
            elif event.button == 5:
                self.overlord_scroll_y = min(self.overlord_max_scroll, self.overlord_scroll_y + 80)
        elif hasattr(pygame, 'MOUSEWHEEL') and event.type == pygame.MOUSEWHEEL:
            self.overlord_scroll_y = max(0, min(self.overlord_max_scroll, self.overlord_scroll_y - event.y * 80))

        for card in self.overlord_cards:
            if card['fight_btn'].is_clicked(event):
                meta = card['meta']
                if meta['level'] == 1 and self.player.arena_rank < meta['required_rank']:
                    self.overlord_msg = f"Rank {meta['required_rank']} required to challenge {meta['title']}."
                    self.overlord_msg_t = 2.5
                elif self.player.overlord_unlocked < meta['level']:
                    self.overlord_msg = f"Defeat Overlord {meta['level'] - 1} to unlock {meta['title']}."
                    self.overlord_msg_t = 2.5
                else:
                    sounds.play('button_click')
                    self._start_overlord_fight(meta)
                return

    def _draw_overlord(self, surface):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))

        pr = self.overlord_panel if hasattr(self, 'overlord_panel') else pygame.Rect((SCREEN_W - 1150) // 2, (SCREEN_H - 760) // 2, 1150, 760)
        draw_panel(surface, pr, color=(18, 12, 22), border=GOLD)

        header_r = pygame.Rect(pr.x + 24, pr.y + 20, pr.width - 48, 132)
        draw_panel(surface, header_r, color=(36, 18, 42), border=GOLD, radius=16, alpha=230)
        draw_text(surface, 'OVERLORD HALL', header_r.centerx, header_r.y + 18,
                  38, GOLD, bold=True, center=True)
        draw_text(surface, 'A grand raid selection chamber where mighty bosses await the worthy.',
                  header_r.centerx, header_r.y + 56, 16, PARCHMENT, center=True)
        draw_text(surface,
                  f'Current rank: #{self.player.arena_rank}  ·  Overlords cleared: {max(0, self.player.overlord_unlocked - 1)}',
                  header_r.centerx, header_r.y + 92, 14, STONE_LT, center=True)

        footer_h = 106
        content_top = pr.y + header_r.height + 34
        content_rect = pygame.Rect(pr.x + 24, content_top, pr.width - 48, pr.height - footer_h - content_top + pr.y - 12)
        draw_panel(surface, content_rect, color=(20, 12, 24), border=(70, 24, 80), radius=16)

        inner_pad = 18
        scroll_area = pygame.Rect(content_rect.x + inner_pad, content_rect.y + inner_pad,
                                  content_rect.w - inner_pad * 2 - 16, content_rect.h - inner_pad * 2)
        draw_panel(surface, scroll_area, color=(16, 10, 18), border=(90, 40, 110), radius=12)

        card_h = 240
        gap = 24
        total_height = len(self.overlord_cards) * (card_h + gap) - gap
        self.overlord_max_scroll = max(0, total_height - scroll_area.h)
        self.overlord_scroll_y = max(0, min(self.overlord_scroll_y, self.overlord_max_scroll))

        old_clip = surface.get_clip()
        surface.set_clip(scroll_area)

        for card in self.overlord_cards:
            card_rect = card['rect']
            if not card_rect.colliderect(scroll_area):
                continue
            meta = card['meta']
            locked = ((meta['level'] == 1 and self.player.arena_rank < meta['required_rank']) or
                      (meta['level'] > 1 and self.player.overlord_unlocked < meta['level']))
            draw_panel(surface, card_rect, color=(28, 14, 28), border=GOLD, radius=16)

            portrait_r = pygame.Rect(card_rect.x + 20, card_rect.y + 20, 220, card_h - 40)
            draw_panel(surface, portrait_r, color=(12, 8, 14), border=(170, 74, 42), radius=14)
            icon = load_icon(meta.get('portrait', ''), size=(portrait_r.w - 24, portrait_r.h - 24))
            if icon:
                ix = portrait_r.centerx - icon.get_width() // 2
                iy = portrait_r.centery - icon.get_height() // 2
                surface.blit(icon, (ix, iy))
            else:
                draw_text(surface, meta['title'], portrait_r.centerx, portrait_r.centery - 10,
                          16, PARCHMENT, bold=True, center=True)

            info_x = portrait_r.right + 20
            info_width = card_rect.right - info_x - 200
            heading_y = card_rect.y + 24
            draw_text(surface, f'LEVEL {meta["level"]}', info_x, heading_y,
                      18, RED, bold=True)
            draw_text(surface, meta['title'], info_x, heading_y + 28,
                      24, GOLD, bold=True)

            stat_y = heading_y + 68
            draw_text(surface, f'HP: {meta["hp"]}', info_x, stat_y, 14, PARCHMENT)
            draw_text(surface, f'ATK: {meta["damage"]}', info_x, stat_y + 22, 14, PARCHMENT)
            draw_text(surface, f'DEF: {meta["defense"]}', info_x, stat_y + 44, 14, PARCHMENT)

            unlock_text = (
                f'Requires Rank {meta["required_rank"]}' if meta.get('required_rank', 0) > 0 else
                f'Defeat Overlord {meta["level"] - 1}'
            )
            draw_text(surface, unlock_text, info_x, stat_y + 74, 13, STONE_LT)
            draw_text(surface, 'Potential Rewards', info_x, stat_y + 104, 15, GOLD, bold=True)

            rewards_x = info_x
            rewards_y = stat_y + 132
            icon_size = 52
            row_height = icon_size + 18
            columns = 4
            current_col = 0
            current_row = 0

            for group in meta['drops']:
                draw_text(surface, group['category'], rewards_x, rewards_y + current_row * row_height,
                          13, PURPLE, bold=True)
                current_row += 1
                for item_name in group['items']:
                    item_x = rewards_x + current_col * (icon_size + 18)
                    item_y = rewards_y + current_row * row_height
                    frame_r = pygame.Rect(item_x, item_y, icon_size + 14, icon_size + 14)
                    draw_panel(surface, frame_r, color=(18, 10, 18), border=GOLD, radius=12)
                    item_icon = load_icon(item_name, size=(icon_size, icon_size))
                    if item_icon:
                        ix = frame_r.centerx - item_icon.get_width() // 2
                        iy = frame_r.centery - item_icon.get_height() // 2
                        surface.blit(item_icon, (ix, iy))
                    current_col += 1
                    if current_col >= columns:
                        current_col = 0
                        current_row += 1
                if current_col != 0:
                    current_col = 0
                    current_row += 1

            if locked:
                lock_overlay = pygame.Surface((card_rect.w, card_rect.h), pygame.SRCALPHA)
                lock_overlay.fill((0, 0, 0, 160))
                surface.blit(lock_overlay, card_rect.topleft)
                draw_text(surface, 'LOCKED', card_rect.centerx, card_rect.centery - 12,
                          28, STONE_LT, bold=True, center=True)
                draw_text(surface, unlock_text, card_rect.centerx, card_rect.centery + 20,
                          14, STONE_LT, center=True)

            card['fight_btn'].draw(surface)

        surface.set_clip(old_clip)

        if self.overlord_max_scroll > 0:
            scrollbar_r = pygame.Rect(scroll_area.right + 8, scroll_area.y, 12, scroll_area.h)
            pygame.draw.rect(surface, (45, 18, 55), scrollbar_r, border_radius=6)
            thumb_h = max(50, int(scroll_area.h * (scroll_area.h / max(1, total_height))))
            thumb_y = scroll_area.y + int((self.overlord_scroll_y / max(1, self.overlord_max_scroll)) * (scroll_area.h - thumb_h))
            pygame.draw.rect(surface, (220, 145, 255), (scrollbar_r.x + 2, thumb_y, scrollbar_r.w - 4, thumb_h), border_radius=6)

        footer_r = pygame.Rect(pr.x + 24, pr.bottom - footer_h + 10, pr.width - 48, footer_h - 24)
        draw_panel(surface, footer_r, color=(32, 18, 30), border=(120, 60, 160), radius=14)
        draw_text(surface, 'COMING SOON', footer_r.centerx, footer_r.y + 18,
                  18, PARCHMENT, bold=True, center=True)
        draw_text(surface, 'More overlords and secret treasures are arriving soon.',
                  footer_r.centerx, footer_r.y + 44, 12, STONE_LT, center=True)

        if self.overlord_msg:
            draw_text(surface, self.overlord_msg, pr.centerx, pr.bottom - 18,
                      16, GREEN, bold=True, center=True)

        if self.overlord_back_btn:
            self.overlord_back_btn.draw(surface)

    def _handle_campfire(self, event):
        for btn in self.cf_buttons:
            if btn.is_clicked(event):
                sounds.play('button_click')
                if btn.text == 'FIGHT!':
                    self.state = ST_ARENA
                elif btn.text == 'SHOP':
                    # Reuse shop instance if it exists, otherwise create new one
                    if self.shop is None:
                        self.shop = Shop(SCREEN_W, SCREEN_H)
                    self.state = ST_SHOP
                elif btn.text == 'INVENTORY':
                    self.state = ST_INV
                    self._build_inventory_ui()
                elif btn.text == 'OVERLORD':
                    self.state = ST_OVERLORD
                    self._build_overlord_menu()
                elif btn.text == 'SAVE':
                    SaveSystem.save(self.player, shop_data=self.shop.to_dict() if self.shop else None)
                    self.cf_msg   = 'Game saved!'
                    self.cf_msg_t = 2.0
                elif btn.text == 'MENU':
                    self.state = ST_MENU

    def _draw_campfire(self, surface):
        if not self.player:
            return
        t = self.cf_t

        # Ambient overlay
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,60))
        surface.blit(ov, (0,0))

        # Central campfire
        fx, fy = SCREEN_W//2, SCREEN_H - 120
        if not self.campfire_hidden:
            if random.random() < 0.4:
                particles.emit_fire(fx + random.randint(-12,12), fy, 4)
                particles.emit_smoke(fx, fy - 30, 2)
        # Logs
        pygame.draw.rect(surface, DARK_BROWN, (fx-30, fy+5, 60, 12), border_radius=4)
        pygame.draw.rect(surface, DARK_BROWN,
                         (int(fx-20+math.sin(0.5)*20), fy+10, 50, 10), border_radius=4)

        # Panel
        pw, ph = 520, 560
        pr = pygame.Rect(SCREEN_W//2 - pw//2, SCREEN_H//2 - ph//2 - 40, pw, ph)
        draw_panel(surface, pr, color=(25,20,18), border=GOLD)

        header_r = pygame.Rect(pr.x + 16, pr.y + 16, pr.width - 32, 112)
        draw_panel(surface, header_r, color=(40,35,30), border=GOLD, radius=10, alpha=220)
        draw_text(surface, f'Welcome, {self.player.name}!',
                  header_r.centerx, header_r.y + 12, 24, GOLD, bold=True, center=True)
        draw_text(surface, f'{self.player.class_name}  ·  Level {self.player.level}',
                  header_r.centerx, header_r.y + 42, 16, PARCHMENT, center=True)
        draw_text(surface, f'Rank #{self.player.arena_rank}  ·  {self.player.wins}W / {self.player.losses}L',
                  header_r.centerx, header_r.y + 62, 14, STONE_LT, center=True)
        draw_text(surface, f'Gold: {self.player.inventory.gold}g',
                  header_r.x + 16, header_r.y + 16, 18, GOLD, bold=True)

        if self.cf_msg:
            draw_text(surface, self.cf_msg, SCREEN_W//2, SCREEN_H-40,
                      20, GREEN, bold=True, center=True)

        for btn in self.cf_buttons:
            btn.draw(surface)

    # ═══════════════════════════════════════════════════════════
    #  COMBAT
    # ═══════════════════════════════════════════════════════════

    def _start_fight(self):
        enemy_type = self.arena_sys.pick_enemy_type(self.player)
        level_scale = max(1, self.player.level)
        self.enemy = Enemy(enemy_type, level_scale)
        self.in_overlord_fight = False
        self.current_overlord_level = 0
        self.combat_phase = 'intro'
        self.intro_timer  = 2.5
        self.turn_number  = 0
        self.heavy_cooldown = 0
        self.combat_arena_tier = self.arena_sys.get_current_tier(self.player)
        self.state = ST_COMBAT
        self._build_combat_buttons()
        self.hud.combat_log.clear()
        # CRITICAL FIX: Fully restore HP and MP before every new fight
        self.player.hp = self.player.max_hp
        self.player.mp = self.player.max_mp
        # reset one-time flags
        self._victory_processed = False
        self._gameover_processed = False

    def _start_overlord_fight(self, meta):
        # start a special overlord boss encounter
        self.enemy = Enemy('Slave', max(1, meta['level'] * 2))
        self.enemy.name = meta['title']
        self.enemy.type = 'Overlord'
        self.enemy.ai_type = 'boss'
        self.enemy.max_hp = meta['hp']
        self.enemy.hp = meta['hp']
        self.enemy.strength = meta['damage']
        self.enemy.defense = meta['defense']
        self.enemy.level = max(1, meta['level'] * 3)
        self.enemy.xp_reward = max(50, meta['hp'] // 3)
        self.enemy.gold_reward = max(75, meta['level'] * 200)
        self.enemy.weapon = self.enemy.weapon or 'Hammer'
        self.enemy.equipment.equip(Item(self.enemy.weapon))
        self.in_overlord_fight = True
        self.current_overlord_level = meta['level']
        self.combat_phase = 'intro'
        self.intro_timer = 2.5
        self.turn_number = 0
        self.heavy_cooldown = 0
        self.combat_arena_tier = 0
        self.state = ST_COMBAT
        self._build_combat_buttons()
        self.hud.combat_log.clear()
        self.player.hp = self.player.max_hp
        self.player.mp = self.player.max_mp
        self._victory_processed = False
        self._gameover_processed = False

    def _build_combat_buttons(self):
        bw, bh = 140, 48
        by = SCREEN_H - 64
        bx = SCREEN_W//2 - 2*(bw+10)//2
        skill = _get_player_skill(self.player)
        special_text = 'SPECIAL'
        if skill and 'mp' in skill:
            special_text = f'SPECIAL ({skill["mp"]}MP)'
        self.combat_buttons = [
            Button(bx,            by, bw, bh, 'ATTACK',   18, color=(140,40,20), hover_color=RED),
            Button(bx+bw+10,      by, bw, bh, 'HEAVY',    18, color=(100,30,20), hover_color=(180,50,20)),
            Button(bx+(bw+10)*2,  by, bw, bh, special_text,  18, color=(80,30,140), hover_color=PURPLE),
        ]

    def _update_combat(self, dt, ms):
        skill = _get_player_skill(self.player)
        special_cost = skill.get('mp', 0) if skill else 0
        for btn in self.combat_buttons:
            btn.update(dt, ms)
            btn.enabled = (self.combat_phase == 'player_turn')
            if self.combat_phase == 'player_turn':
                if btn.text.startswith('HEAVY') and self.heavy_cooldown > 0:
                    btn.enabled = False
                if btn.text.startswith('SPECIAL') and self.player.mp < special_cost:
                    btn.enabled = False

        if self.combat_msg_timer > 0:
            self.combat_msg_timer -= dt

        if self.combat_phase == 'intro':
            self.intro_timer -= dt
            if self.intro_timer <= 0:
                self.combat_phase = 'player_turn'
                self.hud.add_log(f'Fight! {self.player.name} vs {self.enemy.name}!', GOLD)

        elif self.combat_phase == 'enemy_anim':
            self.anim_timer -= dt
            if self.anim_timer <= 0:
                self._enemy_take_turn()

        elif self.combat_phase == 'result_pause':
            self.anim_timer -= dt
            if self.anim_timer <= 0:
                if not self.player.alive:
                    self._on_player_death()
                elif not self.enemy.alive:
                    self._on_enemy_death()
                else:
                    if self.heavy_cooldown > 0:
                        self.heavy_cooldown -= 1
                    self.combat_phase = 'player_turn'
                    self.player.tick_status()
                    self.turn_number += 1

    def _handle_combat(self, event):
        if self.combat_phase != 'player_turn':
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, name in self.potion_slot_rects:
                if rect.collidepoint(event.pos):
                    self._use_potion(name)
                    return
        actions = ['attack','heavy_attack','special']
        for i, btn in enumerate(self.combat_buttons):
            if btn.is_clicked(event):
                action = actions[i]
                self._player_take_action(action)
                return

    def _player_take_action(self, action):
        if action == 'special':
            skill = _get_player_skill(self.player)
            special_cost = skill.get('mp', 0) if skill else 0
            if self.player.mp < special_cost:
                self.hud.add_log('Not enough mana!', RED)
                return
        result = Combat.player_attack(self.player, self.enemy, action)
        if action == 'heavy_attack':
            self.heavy_cooldown = 2
        self.combat_phase = 'enemy_anim'
        self.anim_timer   = 0.5

        # Animate player
        if action == 'attack':
            self.player.renderer.set_state('attack')
            sounds.play('sword_slash')
        elif action == 'heavy_attack':
            self.player.renderer.set_state('heavy_attack')
            sounds.play('heavy_hit')
        elif action == 'special':
            self.player.renderer.set_state('attack')
            sounds.play('critical')

        if result.damage > 0:
            self.enemy.renderer.set_state('hurt')
            sounds.play('sword_hit')
            ex = int(self.enemy.renderer.x)
            ey = int(self.enemy.renderer.y - 80)
            if result.is_crit:
                self.hud.float_damage(result.damage, ex, ey, is_crit=True)
                self.effects.shake(14, 0.3)
                self.effects.freeze(0.1)
                self.effects.flash((255,200,50), 0.12)
                self.effects.slowmo(0.5, 0.25)
                particles.emit_critical(ex, ey)
                sounds.play('critical')
            else:
                self.hud.float_damage(result.damage, ex, ey)
                self.effects.shake(7, 0.18)
                particles.emit_blood(ex, ey, count=8)
                particles.emit_sparks(ex, ey, 6)
        elif result.is_miss:
            self.hud.float_damage(0, self.enemy.renderer.x, self.enemy.renderer.y-80,
                                   is_miss=True)
            sounds.play('miss')
        self.hud.add_log(result.message)

        if self.enemy and not self.enemy.alive:
            self.hud.ftm.texts.clear()
            self.hud.add_log('Victory!', GOLD)
            self._on_enemy_death()
            return

    def _enemy_take_turn(self):
        if not self.enemy or not self.enemy.alive:
            return
        action = self.enemy.decide_action(self.player.hp, self.player.max_hp, self.turn_number)
        result = Combat.enemy_attack(self.enemy, self.player, action)

        # Animate enemy
        anim_map = {'attack':'attack','heavy_attack':'heavy_attack',
                     'taunt':'taunt','defend':'block','potion':'idle','stunned':'hurt'}
        self.enemy.renderer.set_state(anim_map.get(action, 'idle'))

        if result.damage > 0:
            self.player.renderer.set_state('hurt')
            px = int(self.player.renderer.x)
            py = int(self.player.renderer.y - 80)
            if result.is_crit:
                self.hud.float_damage(result.damage, px, py, is_crit=True)
                self.effects.shake(16, 0.35)
                self.effects.freeze(0.1)
                self.effects.flash((200,30,30), 0.15)
                sounds.play('critical')
                particles.emit_critical(px, py)
            else:
                self.hud.float_damage(result.damage, px, py)
                self.effects.shake(8, 0.2)
                sounds.play('sword_hit')
                particles.emit_blood(px, py, 6, math.pi)
        elif result.is_heal > 0:
            sounds.play('potion')
            ex = int(self.enemy.renderer.x)
            self.hud.float_damage(result.is_heal, ex, self.enemy.renderer.y-80, is_heal=True)
            particles.emit_magic(ex, self.enemy.renderer.y-60, 12, (60,200,60))
        elif result.is_miss:
            sounds.play('miss')

        self.hud.add_log(result.message, (220,100,100))
        if self.enemy and not self.enemy.alive:
            self.hud.ftm.texts.clear()
            self.hud.add_log('Victory!', GOLD)
            self._on_enemy_death()
            return
        self.combat_phase = 'result_pause'
        self.anim_timer   = 0.6

    def _use_potion(self, item_name=None):
        if item_name:
            item = next((i for i in self.player.inventory.items
                         if i.type == 'consumable' and i.name == item_name), None)
        else:
            item = next((i for i in self.player.inventory.items if i.type == 'consumable'), None)
        if not item:
            self.hud.add_log('No potions!', RED)
            return
        res  = self.player.use_item(item)
        sounds.play('potion')
        if res.get('heal'):
            self.hud.float_damage(res['heal'], self.player.renderer.x,
                                   self.player.renderer.y - 80, is_heal=True)
            particles.emit_magic(self.player.renderer.x, self.player.renderer.y-60,
                                  10, (60,220,60))
        if res.get('mp'):
            self.hud.float_damage(res['mp'], self.player.renderer.x + 30,
                                   self.player.renderer.y - 80, is_magic=True)
        self.hud.add_log(f'Used {item.name}!', GREEN)
        self.combat_phase = 'enemy_anim'
        self.anim_timer   = 0.5

    def _draw_potion_inventory(self, surface):
        panel_w = 360
        panel_h = 110
        start_x = 16
        start_y = SCREEN_H - panel_h - 16
        panel_r = pygame.Rect(start_x, start_y, panel_w, panel_h)
        draw_panel(surface, panel_r, color=(28,18,14), border=GOLD, radius=12)
        draw_text(surface, 'POTIONS', panel_r.centerx, panel_r.y + 10, 16, GOLD, bold=True, center=True)

        slot_size = 58
        slot_gap = 10
        base_x = panel_r.x + 12
        base_y = panel_r.y + 34
        potion_names = ['Health Potion', 'Mana Potion', 'Elixir', 'Rage Potion']
        self.potion_slot_rects = []
        for i, name in enumerate(potion_names):
            rect = pygame.Rect(base_x + i * (slot_size + slot_gap), base_y, slot_size, slot_size)
            qty = self.player.inventory.count(name)
            bg_col = (34, 24, 18) if qty == 0 else (48, 34, 22)
            pygame.draw.rect(surface, bg_col, rect, border_radius=10)
            pygame.draw.rect(surface, GOLD, rect, 2, border_radius=10)
            icon = load_icon(name, size=(40, 40))
            if icon:
                icon_rect = icon.get_rect(center=rect.center)
                surface.blit(icon, icon_rect)
            qty_text = f'x{qty}'
            text_col = WHITE if qty > 0 else BRONZE
            draw_text(surface, qty_text, rect.centerx, rect.bottom + 4, 14, text_col, center=True, shadow=False)
            self.potion_slot_rects.append((rect, name))

    def _on_enemy_death(self):
        # Prevent repeated processing (one-time only)
        if self._victory_processed:
            return
        self._victory_processed = True
        # If we've already moved to victory state elsewhere, bail
        if self.state == ST_VICTORY:
            return
        try:
            if self.hud:
                self.hud.ftm.texts.clear()
                self.hud.add_log('Victory!', GOLD)
            self.enemy.renderer.set_state('death')
            self.player.renderer.set_state('victory')
            sounds.play('crowd_cheer')
            sounds.play('victory')
            self.effects.flash(GOLD_LT, 0.2)
            self.effects.shake(8, 0.3)
            particles.emit_sparks(self.enemy.renderer.x, self.enemy.renderer.y-60, 30)

            # Rewards
            xp_gained    = getattr(self.enemy, 'xp_reward', 0)
            gold_gained  = getattr(self.enemy, 'gold_reward', 0)
            levels       = self.player.add_xp(xp_gained)
            # ensure inventory exists
            if not hasattr(self.player, 'inventory') or self.player.inventory is None:
                self.player.inventory = Inventory()
            try:
                self.player.inventory.gold += gold_gained
            except Exception:
                # fallback: set gold directly
                try:
                    self.player.inventory.gold = int(gold_gained)
                except Exception:
                    pass
            self.player.wins  += 1
            self.player.kills += 1
            self.player.arena_rank = min(15, self.player.arena_rank +
                                         (1 if self.player.wins % 3 == 0 else 0))
            is_boss = getattr(self.enemy, 'ai_type', '') == 'boss'
            # Generate loot defensively; overlord fights may yield secret prismatic rewards
            try:
                self.victory_loot = Item.generate_loot(
                    level=getattr(self.enemy, 'level', 1),
                    is_boss=is_boss,
                    drop_count=(3 if self.in_overlord_fight else (2 if is_boss else 1)),
                    allow_prismatic=self.in_overlord_fight,
                    prismatic_chance=(0.15 if self.in_overlord_fight else 0.0)
                ) or []
                if (is_boss or self.in_overlord_fight) and not self.victory_loot:
                    self.victory_loot = Item.generate_loot(
                        level=getattr(self.enemy, 'level', 1),
                        is_boss=is_boss,
                        drop_count=1,
                        allow_prismatic=self.in_overlord_fight,
                        prismatic_chance=(0.15 if self.in_overlord_fight else 0.0)
                    ) or []
            except Exception:
                self.victory_loot = []
            if self.in_overlord_fight:
                self.player.overlord_unlocked = max(self.player.overlord_unlocked, self.current_overlord_level + 1)
                self.in_overlord_fight = False
                self.current_overlord_level = 0
            for item in self.victory_loot:
                try:
                    self.player.inventory.add(item)
                except Exception:
                    pass
            # Save game, but don't let save errors crash the game
            try:
                SaveSystem.save(self.player)
            except Exception:
                import traceback
                tb = traceback.format_exc()
                try:
                    with open('error.log', 'a', encoding='utf-8') as f:
                        f.write('\n[Save Error]\n')
                        f.write(tb)
                except Exception:
                    pass

            self.victory_xp   = xp_gained
            self.victory_gold = gold_gained
            self.victory_levels = levels
            self.state        = ST_VICTORY
            self._build_victory_screen()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            try:
                with open('error.log', 'a', encoding='utf-8') as f:
                    f.write('\n[Enemy Death Error]\n')
                    f.write(tb)
            except Exception:
                pass
            # Fallback: move to victory state with minimal data to avoid crash
            self.victory_loot = []
            self.victory_xp = getattr(self.enemy, 'xp_reward', 0) if getattr(self, 'enemy', None) else 0
            self.victory_gold = getattr(self.enemy, 'gold_reward', 0) if getattr(self, 'enemy', None) else 0
            self.victory_levels = self.player.add_xp(self.victory_xp) if hasattr(self.player, 'add_xp') else []
            self.state = ST_VICTORY
            try:
                self._build_victory_screen()
            except Exception:
                pass

    def _on_player_death(self):
        # Prevent repeated processing (one-time only)
        if self._gameover_processed:
            return
        self._gameover_processed = True
        # If we've already moved to gameover state elsewhere, bail
        if self.state == ST_GAMEOVER:
            return
        self.player.renderer.set_state('death')
        sounds.play('defeat')
        self.effects.shake(20, 0.5)
        self.effects.flash((200,20,20), 0.3)
        self.player.losses += 1
        # Persist death immediately so retry/load shows updated losses
        try:
            SaveSystem.save(self.player)
        except Exception:
            pass
        self.state = ST_GAMEOVER
        self._build_gameover()

    def _draw_combat(self, surface):
        if not self.enemy or not self.player:
            return
        bg = self._get_arena_tier_background(getattr(self, 'combat_arena_tier', 0))
        if bg:
            self._draw_background(surface, bg)

        t = getattr(self, 'cf_t', 0)

        # Arena intro overlay
        if self.combat_phase == 'intro':
            self._draw_intro_banner(surface)

        # Position gladiators
        floor_y = int(SCREEN_H * 0.78)
        self.player.renderer.x = SCREEN_W // 4
        self.player.renderer.y = floor_y
        self.player.renderer.facing = 1

        self.enemy.renderer.x = (SCREEN_W * 3) // 4
        self.enemy.renderer.y = floor_y
        self.enemy.renderer.facing = -1

        # Shadows
        shadow_w = int(60 * self.player.renderer.scale)
        pygame.draw.ellipse(surface, (30,20,10),
                            (self.player.renderer.x - shadow_w//2,
                             floor_y - 8, shadow_w, 14))
        shadow_w2 = int(60 * self.enemy.renderer.scale)
        pygame.draw.ellipse(surface, (30,20,10),
                            (self.enemy.renderer.x - shadow_w2//2,
                             floor_y - 8, shadow_w2, 14))

        # Draw gladiators
        self.player.renderer.draw(surface, self.player.equipment)
        self.enemy.renderer.draw(surface, self.enemy.equipment)

        # HUD
        self.hud.draw(surface, self.player, self.enemy)

        # Combat buttons

        # Combat buttons
        if self.combat_phase == 'player_turn':
            draw_text(surface, 'YOUR TURN — Choose an action:',
                      SCREEN_W//2, SCREEN_H - 88, 16, PARCHMENT, center=True)
        elif self.combat_phase == 'enemy_anim':
            draw_text(surface, "Enemy's turn...",
                      SCREEN_W//2, SCREEN_H - 88, 16, (220,80,80), center=True)
        for btn in self.combat_buttons:
            btn.draw(surface)

        if self.heavy_cooldown > 0 and len(self.combat_buttons) > 1:
            heavy_btn = self.combat_buttons[1]
            overlay = pygame.Surface((heavy_btn.rect.width, heavy_btn.rect.height), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 150), overlay.get_rect(), border_radius=8)
            surface.blit(overlay, heavy_btn.rect.topleft)
            draw_text(surface, f'COOLDOWN {self.heavy_cooldown}',
                      heavy_btn.rect.centerx, heavy_btn.rect.centery - 10,
                      14, WHITE, bold=True, center=True)
            draw_text(surface, 'HEAVY', heavy_btn.rect.centerx,
                      heavy_btn.rect.centery + 8, 14, (220,180,120), bold=True, center=True)

        self._draw_potion_inventory(surface)

        # Turn counter
        draw_text(surface, f'Turn {self.turn_number+1}',
                  SCREEN_W//2, 10, 18, PARCHMENT, center=True)

    def _draw_intro_banner(self, surface):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0,0,0,160))
        surface.blit(overlay, (0,0))
        draw_text(surface, 'VS', SCREEN_W//2, SCREEN_H//2 - 40,
                  80, GOLD, bold=True, center=True)
        draw_text(surface, self.player.name, SCREEN_W//4, SCREEN_H//2 + 20,
                  36, WHITE, bold=True, center=True)
        draw_text(surface, self.enemy.name, SCREEN_W*3//4, SCREEN_H//2 + 20,
                  36, RED, bold=True, center=True)
        draw_text(surface, 'FIGHT!', SCREEN_W//2, SCREEN_H//2 + 70,
                  44, FIRE_ORANGE, bold=True, center=True)

    # ═══════════════════════════════════════════════════════════
    #  VICTORY / GAMEOVER
    # ═══════════════════════════════════════════════════════════

    def _build_victory_screen(self):
        cx = SCREEN_W//2
        self._victory_btns = [
            Button(cx-110, SCREEN_H//2 + 140, 220, 52, 'CONTINUE', 24,
                   color=(30,100,30), hover_color=GREEN),
        ]
        self.victory_t = 0.0

    def _draw_victory(self, surface):
        self.victory_t += self.dt
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,140))
        surface.blit(ov, (0,0))

        # Draw player in victory pose
        if self.player:
            self.player.renderer.x = SCREEN_W//2
            self.player.renderer.y = SCREEN_H//2 + 40
            self.player.renderer.set_state('victory')
            self.player.renderer.draw(surface, self.player.equipment)

        # Particles
        if random.random() < 0.5:
            particles.emit_sparks(self.player.renderer.x, self.player.renderer.y-80, 6)

        pw, ph = 500, 300
        pr = pygame.Rect(SCREEN_W//2-pw//2, SCREEN_H//2-ph//2-120, pw, ph)
        draw_panel(surface, pr, color=BRONZE_DK, border=GOLD)

        draw_text(surface, 'VICTORY!', SCREEN_W//2, pr.y+14,
                  52, GOLD, bold=True, center=True)
        draw_text(surface, f'+{self.victory_xp} XP', SCREEN_W//2, pr.y+80,
                  28, GREEN, bold=True, center=True)
        draw_text(surface, f'+{self.victory_gold} Gold', SCREEN_W//2, pr.y+116,
                  28, GOLD, bold=True, center=True)

        if self.victory_loot:
            loot_text = ', '.join([f'{item.name}' for item in self.victory_loot])
            draw_text(surface, f'Loot: {loot_text}', SCREEN_W//2, pr.y+150,
                      20, PARCHMENT, center=True)
            y_offset = 180
        else:
            draw_text(surface, 'Loot: None this time', SCREEN_W//2, pr.y+150,
                      18, PARCHMENT, center=True)
            y_offset = 180

        if self.victory_levels:
            draw_text(surface, f'LEVEL UP! → Level {self.player.level}',
                      SCREEN_W//2, pr.y+192, 24, FIRE_ORANGE, bold=True, center=True)
            draw_text(surface, f'Wins: {self.player.wins}  |  Rank: #{self.player.arena_rank}',
                      SCREEN_W//2, pr.y+224, 18, PARCHMENT, center=True)
        else:
            draw_text(surface, f'Wins: {self.player.wins}  |  Rank: #{self.player.arena_rank}',
                      SCREEN_W//2, pr.y+192, 18, PARCHMENT, center=True)

        ms = self._fix_mouse_pos(pygame.mouse.get_pos())
        for btn in self._victory_btns:
            btn.update(self.dt, ms)
            btn.draw(surface)

    def _build_gameover(self):
        cx = SCREEN_W//2
        self._gameover_btns = [
            Button(cx-130, SCREEN_H//2+140, 120, 50, 'RETRY', 22,
                   color=BRONZE_DK, hover_color=BRONZE),
            Button(cx+10,  SCREEN_H//2+140, 120, 50, 'MENU',  22,
                   color=(80,30,30), hover_color=(160,50,50)),
        ]

    def _draw_gameover(self, surface):
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,180))
        surface.blit(ov, (0,0))

        pw, ph = 480, 260
        pr = pygame.Rect(SCREEN_W//2-pw//2, SCREEN_H//2-ph//2-80, pw, ph)
        draw_panel(surface, pr, color=(40,10,10), border=BLOOD)

        draw_text(surface, 'DEFEATED!', SCREEN_W//2, pr.y+16,
                  52, RED, bold=True, center=True)
        draw_text(surface, 'You have fallen in the arena...',
                  SCREEN_W//2, pr.y+80, 22, PARCHMENT, center=True)
        if self.player:
            draw_text(surface, f'{self.player.name}  —  Level {self.player.level}',
                      SCREEN_W//2, pr.y+112, 20, GRAY, center=True)
            draw_text(surface, f'Wins: {self.player.wins}  Losses: {self.player.losses}',
                      SCREEN_W//2, pr.y+140, 18, STONE_LT, center=True)

        ms = self._fix_mouse_pos(pygame.mouse.get_pos())
        for btn in self._gameover_btns:
            btn.update(self.dt, ms)
            btn.draw(surface)

    def _restart_from_save(self):
        data = SaveSystem.load()
        if data:
            from src.player import Player
            self.player = Player.from_dict(data['player'])
            self.player.hp = max(1, self.player.max_hp // 3)
            self.state = ST_CAMPFIRE
            self._build_campfire()
        else:
            self.state = ST_MENU

    # ═══════════════════════════════════════════════════════════
    #  INVENTORY
    # ═══════════════════════════════════════════════════════════

    def _build_inventory_ui(self):
        self.inv_selected = None
        self.inv_hover    = None
        self.inv_msg      = ''
        self.inv_msg_t    = 0.0
        # Drag & drop state
        self.inv_dragging = False
        self.inv_drag_origin = None
        self.inv_drag_item = None
        # layout cache
        self.inv_layout = None
        cx = SCREEN_W//2
        # Place buttons inside the right panel, stacked vertically with spacing
        pw, ph = SCREEN_W - 100, SCREEN_H - 80
        pr = pygame.Rect(50, 40, pw, ph)
        left_w = 240
        center_w = 360
        right_w = pw - left_w - center_w - 32
        right_r = pygame.Rect(pr.x+16+left_w+16+center_w+16, pr.y+54, right_w, ph-120)
        btn_w = 130
        btn_h = 42
        btn_gap = 18
        btn_x = right_r.x + (right_r.width - btn_w) // 2
        btn_y_start = right_r.bottom - (btn_h * 2 + btn_gap) - 24
        self.inv_btns = {
            'equip':    Button(btn_x, btn_y_start, btn_w, btn_h, 'EQUIP', 20),
            'drop':     Button(btn_x, btn_y_start + btn_h + btn_gap, btn_w, btn_h, 'DROP', 20,
                                color=(80,30,30), hover_color=RED),
            'close':    Button(cx-65,  SCREEN_H-70, 130, 44, 'CLOSE', 20,
                                color=BRONZE_DK, hover_color=BRONZE),
        }

        # build static layout positions used for drop targets
        pw, ph = SCREEN_W - 100, SCREEN_H - 80
        pr = pygame.Rect(50, 40, pw, ph)
        left_w = 240
        center_w = 360
        # Decrease the width of the right (Bag) border frame for a more compact look
        right_w = max(220, pw - left_w - center_w - 64)  # reduce width and add more margin
        left_r = pygame.Rect(pr.x+16, pr.y+54, left_w, ph-120)
        center_r = pygame.Rect(pr.x+16+left_w+16, pr.y+54, center_w, ph-120)
        right_r = pygame.Rect(center_r.right+24, pr.y+54, right_w, ph-120)
        # equipment slot positions (grid in center)
        slot_positions = {}
        s_cols = 3
        s_size = 64
        sx = center_r.x + (center_r.width - (s_cols * s_size + (s_cols-1)*12))//2
        sy = center_r.y + 20
        slots = Equipment.SLOTS
        for i, slot in enumerate(slots):
            cx_slot = sx + (i % s_cols) * (s_size + 12)
            cy_slot = sy + (i // s_cols) * (s_size + 12)
            slot_positions[slot] = pygame.Rect(cx_slot, cy_slot, s_size, s_size)

        self.inv_layout = {
            'pr': pr, 'left_r': left_r, 'center_r': center_r, 'right_r': right_r,
            'slot_rects': slot_positions
        }

    def _handle_inventory(self, event):
        ms = self._fix_mouse_pos(pygame.mouse.get_pos())
        for key, btn in self.inv_btns.items():
            if btn.is_clicked(event):
                sounds.play('button_click')
                if key == 'close':
                    self.state = ST_CAMPFIRE
                elif key == 'equip' and self.inv_selected:
                    item = self.inv_selected
                    # Prevent equipping consumables from inventory
                    if item.type == 'consumable':
                        self.inv_msg = f'Cannot equip consumables from inventory.'
                        self.inv_msg_t = 2.0
                        return
                    old = self.player.equipment.equip(item)
                    # decrement stack or remove for non-consumables only
                    if getattr(item, 'count', 1) > 1:
                        item.count -= 1
                    else:
                        self.player.inventory.remove(item)
                    if old:
                        self.player.inventory.add(old)
                    self.inv_msg = f'Equipped {item.name}!'
                    self.inv_msg_t = 2.0
                    self.inv_selected = None
                elif key == 'use' and self.inv_selected:
                    if self.inv_selected.type == 'consumable':
                        res = self.player.use_item(self.inv_selected)
                        self.inv_msg = f'Used {self.inv_selected.name}!'
                        self.inv_msg_t = 2.0
                        sounds.play('potion')
                        # clear selection if item consumed
                        if self.inv_selected not in self.player.inventory.items:
                            self.inv_selected = None
                elif key == 'drop' and self.inv_selected:
                    self.player.inventory.remove(self.inv_selected)
                    self.inv_msg = 'Item dropped.'
                    self.inv_msg_t = 2.0
                    self.inv_selected = None
                elif key == 'unequip' and self.inv_selected:
                    for slot, item in self.player.equipment.slots.items():
                        if item and item.name == self.inv_selected.name:
                            old = self.player.equipment.unequip(slot)
                            if old:
                                self.player.inventory.add(old)
                            self.inv_msg = f'Unequipped {old.name}!'
                            self.inv_msg_t = 2.0
                            self.inv_selected = None
                            break
        # Item click and drag/drop
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # click on equipped items to unequip
            if self.inv_layout:
                for slot, rect in self.inv_layout['slot_rects'].items():
                    item = self.player.equipment.slots.get(slot)
                    if item and rect.collidepoint(event.pos):
                        old = self.player.equipment.unequip(slot)
                        if old:
                            self.player.inventory.add(old)
                            self.inv_msg = f'Unequipped {old.name}!'
                            self.inv_msg_t = 2.0
                            self.inv_selected = None
                        break
            for i, item in enumerate(self.player.inventory.items):
                r = self._inv_item_rect(i)
                if r.collidepoint(event.pos):
                    self.inv_selected = item
                    self.inv_dragging = True
                    self.inv_drag_origin = i
                    self.inv_drag_item = item
                    break

        if event.type == pygame.MOUSEMOTION:
            if self.inv_dragging:
                # update hover target
                self.inv_hover = None
                for i, item in enumerate(self.player.inventory.items):
                    r = self._inv_item_rect(i)
                    if r.collidepoint(ms):
                        self.inv_hover = item
                        break
            else:
                self.inv_hover = None
                if self.inv_layout:
                    for slot, rect in self.inv_layout['slot_rects'].items():
                        item = self.player.equipment.slots.get(slot)
                        if item and rect.collidepoint(ms):
                            self.inv_hover = item
                            break
                if not self.inv_hover:
                    for i, item in enumerate(self.player.inventory.items):
                        r = self._inv_item_rect(i)
                        if r.collidepoint(ms):
                            self.inv_hover = item
                            break

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.inv_dragging and self.inv_drag_item:
                # attempt drop onto equipment slot
                if self.inv_layout:
                    for slot, rect in self.inv_layout['slot_rects'].items():
                        if rect.collidepoint(ms):
                            item = self.inv_drag_item
                            # check compatibility
                            if self.player.equipment._slot_matches_item(slot, item):
                                old = self.player.equipment.equip(item, preferred_slot=slot)
                                if getattr(item, 'count', 1) > 1:
                                    item.count -= 1
                                else:
                                    try:
                                        self.player.inventory.remove(item)
                                    except Exception:
                                        pass
                                if old:
                                    self.player.inventory.add(old)
                                self.inv_msg = f'Equipped {item.name}!'
                                self.inv_msg_t = 2.0
                            break
                # clear dragging state
                self.inv_dragging = False
                self.inv_drag_origin = None
                self.inv_drag_item = None

    def _inv_item_rect(self, i):
        # Center the item grid horizontally in the Bag (right panel)
        iw, ih = 100, 60
        pad = 8
        if hasattr(self, 'inv_layout') and self.inv_layout:
            r = self.inv_layout['right_r']
            # Calculate max columns that fit
            max_cols = max(1, (r.width - 2 * pad) // (iw + pad))
            n_items = len(self.player.inventory.items)
            # Use as many rows as needed, but center the last row
            cols = min(max_cols, n_items) if n_items > 0 else 1
            rows = (n_items + cols - 1) // cols if cols else 1
            # For each row, center the items
            row = i // cols
            col = i % cols
            # For the last row, may have fewer items
            if row == rows - 1:
                last_row_items = n_items - (rows - 1) * cols
                row_cols = last_row_items
            else:
                row_cols = cols
            total_grid_width = row_cols * iw + (row_cols - 1) * pad
            ox = r.x + (r.width - total_grid_width) // 2
            oy = r.y + pad + row * (ih + pad)
            # For last row, center only the items in that row
            if row == rows - 1:
                col_in_row = i % cols
                return pygame.Rect(ox + col_in_row * (iw + pad), oy, iw, ih)
            else:
                return pygame.Rect(ox + col * (iw + pad), oy, iw, ih)
        # fallback
        cols = 5
        ox = 80; oy = 300
        return pygame.Rect(ox + (i%cols)*(iw+6), oy + (i//cols)*(ih+6), iw, ih)

    def _draw_inventory(self, surface):
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,150))
        surface.blit(ov, (0,0))

        ms = self._fix_mouse_pos(pygame.mouse.get_pos())
        if self.inv_msg_t > 0:
            self.inv_msg_t -= self.dt
        else:
            self.inv_msg = ''

        pw, ph = SCREEN_W - 100, SCREEN_H - 80
        pr = pygame.Rect(50, 40, pw, ph)
        draw_panel(surface, pr, color=STONE, border=GOLD)

        draw_text(surface, 'INVENTORY', SCREEN_W//2, pr.y+14, 30, GOLD, bold=True, center=True)

        # Draw three-panel layout (left: stats, center: equipment, right: inventory)
        if self.inv_layout:
            left_r = self.inv_layout['left_r']
            center_r = self.inv_layout['center_r']
            right_r = self.inv_layout['right_r']
        else:
            left_r = pygame.Rect(pr.x+16, pr.y+54, 220, pr.height-120)
            center_r = pygame.Rect(left_r.right+16, pr.y+54, 360, pr.height-120)
            right_r = pygame.Rect(center_r.right+16, pr.y+54, 320, pr.height-120)

        # Left: Stats
        draw_panel(surface, left_r, color=DARK_GRAY, border=BRONZE)
        draw_text(surface, 'Stats', left_r.x+8, left_r.y+6, 16, GOLD, bold=True)
        stats = [
            ('Level',    self.player.level),
            ('HP',       f'{self.player.max_hp}'),
            ('MP',       f'{self.player.max_mp}'),
            ('STR',      self.player.strength),
            ('DEF',      f'{self.player.defense}(+{self.player.equipment.total_defense})'),
            ('AGI',      self.player.agility),
            ('CRIT',     f'{self.player.crit_chance}%'),
            ('DODGE',    f'{self.player.dodge_chance}%'),
        ]
        for i, (k, v) in enumerate(stats):
            draw_text(surface, f'{k}: {v}', left_r.x+12, left_r.y+28 + i*24, 14, PARCHMENT)

        # Center: Equipment slots
        draw_panel(surface, center_r, color=DARK_GRAY, border=BRONZE)
        draw_text(surface, 'Equipment', center_r.x+8, center_r.y+6, 16, GOLD, bold=True)
        # draw each slot rect
        for slot, rect in self.inv_layout['slot_rects'].items():
            item = self.player.equipment.slots.get(slot)
            lbl = slot.replace('_', ' ').title()
            hover_equipment = item and rect.collidepoint(ms)
            border_color = item.color if hover_equipment else BRONZE
            draw_panel(surface, rect, color=DARK_GRAY, border=border_color)
            if item:
                try:
                    icon = load_icon(item.name, size=(rect.width-12, rect.height-24))
                    if icon:
                        ix = rect.centerx - icon.get_width()//2
                        iy = rect.y + 10
                        surface.blit(icon, (ix, iy))
                except Exception:
                    pass
                draw_text(surface, lbl, rect.centerx, rect.bottom-20, 11, PARCHMENT,
                          center=True)
                if hover_equipment:
                    self.inv_hover = item
            else:
                draw_text(surface, lbl, rect.centerx, rect.centery-8, 12, STONE_LT,
                          center=True)

        # Right: Inventory grid
        draw_panel(surface, right_r, color=DARK_GRAY, border=BRONZE)
        draw_text(surface, 'Bag', right_r.x+8, right_r.y+6, 16, GOLD, bold=True)
        self.inv_hover = None
        for i, item in enumerate(self.player.inventory.items):
            r = self._inv_item_rect(i)
            sel = (item == self.inv_selected)
            hov = r.collidepoint(ms)
            if hov:
                self.inv_hover = item
            bg = BRONZE_DK if sel else DARK_GRAY
            draw_panel(surface, r, color=bg, border=item.color if sel else BRONZE)
            draw_text(surface, item.name,  r.x+6, r.y+6,  13, item.color, bold=sel)
            draw_text(surface, item.slot.title() if item.slot else item.type.title(),  r.x+6, r.y+24, 10, STONE_LT)
            # icon
            try:
                icon = load_icon(item.name, size=(40,40))
                if icon:
                    ix = r.right - 48
                    iy = r.y + (r.height - icon.get_height())//2
                    surface.blit(icon, (ix, iy))
            except Exception:
                pass
            # stats
            sx = r.x + 4
            if item.dmg:   draw_text(surface, f'D:{item.dmg}',   r.x+6,  r.y+34, 10, PARCHMENT)
            if item.defense: draw_text(surface, f'Def:{item.defense}', r.x+54, r.y+34, 10, PARCHMENT)
            if item.heal:  draw_text(surface, f'Heal:{item.heal}', r.x+6, r.y+34, 10, GREEN)
            # count
            if getattr(item, 'count', 1) > 1:
                draw_text(surface, f'x{item.count}', r.right-28, r.bottom-20, 12, PARCHMENT, bold=True)



        # Action buttons
        for key, btn in self.inv_btns.items():
            btn.update(self.dt, ms)
            btn.draw(surface)

        if self.inv_msg:
            draw_text(surface, self.inv_msg, SCREEN_W//2, pr.bottom-40,
                      18, GREEN, bold=True, center=True)

        # Tooltip
        if self.inv_hover:
            draw_tooltip(surface, self.inv_hover, ms[0], ms[1])

    # ═══════════════════════════════════════════════════════════
    #  OPTIONS
    # ═══════════════════════════════════════════════════════════

    def _open_options(self):
        self.state = ST_OPTIONS
        cx = SCREEN_W//2
        self.opt_btns = {
            'sfx_dn':      Button(cx-105, 300, 50, 36, '-', 22),
            'sfx_up':      Button(cx+55,  300, 50, 36, '+', 22),
            'mus_dn':      Button(cx-105, 360, 50, 36, '-', 22),
            'mus_up':      Button(cx+55,  360, 50, 36, '+', 22),
            'screen_toggle': Button(cx-105, 420, 210, 42, 'TOGGLE SCREEN', 18,
                                    color=(100,100,100), hover_color=(160,160,160)),
            'del_save':    Button(cx-80,  480, 160, 42, 'DELETE SAVE', 18,
                                    color=(80,20,20), hover_color=RED),
            'back':        Button(cx-65,  540, 130, 44, 'BACK', 20,
                                    color=BRONZE_DK, hover_color=BRONZE),
        }

    def _update_options(self, dt, ms):
        for btn in self.opt_btns.values():
            btn.update(dt, ms)

    def _handle_options(self, event):
        for key, btn in self.opt_btns.items():
            if btn.is_clicked(event):
                sounds.play('button_click')
                if key == 'sfx_up':
                    sounds.set_sfx_vol(sounds.sfx_vol + 0.1)
                elif key == 'sfx_dn':
                    sounds.set_sfx_vol(sounds.sfx_vol - 0.1)
                elif key == 'mus_up':
                    sounds.set_mus_vol(sounds.mus_vol + 0.1)
                elif key == 'mus_dn':
                    sounds.set_mus_vol(sounds.mus_vol - 0.1)
                elif key == 'screen_toggle':
                    new_mode = 'fullscreen' if self.screen_mode != 'fullscreen' else 'default'
                    self._set_screen_mode(new_mode)
                elif key == 'del_save':
                    SaveSystem.delete()
                elif key == 'back':
                    self.state = ST_MENU
                    self._build_menu()

    def _draw_options(self, surface):
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,160))
        surface.blit(ov, (0,0))

        pw, ph = 500, 400
        pr = pygame.Rect(SCREEN_W//2-pw//2, SCREEN_H//2-ph//2, pw, ph)
        draw_panel(surface, pr, color=STONE, border=GOLD)

        draw_text(surface, 'OPTIONS', SCREEN_W//2, pr.y+16, 32, GOLD, bold=True, center=True)

        cx = SCREEN_W//2
        label_x = pr.x + 40
        value_x = cx

        draw_text(surface, 'SFX Volume:', label_x, 310, 18, PARCHMENT)
        draw_text(surface, f'{int(sounds.sfx_vol*100)}%', value_x, 310, 18, GOLD, bold=True, center=True)
        draw_text(surface, 'Music Volume:', label_x, 370, 18, PARCHMENT)
        draw_text(surface, f'{int(sounds.mus_vol*100)}%', value_x, 370, 18, GOLD, bold=True, center=True)

        mode_label = 'Fullscreen' if self.screen_mode == 'fullscreen' else f'Default ({SCREEN_W}x{SCREEN_H})'
        draw_text(surface, 'Screen Mode:', label_x, 430, 18, PARCHMENT)
        draw_text(surface, mode_label, value_x, 430, 18, GOLD, bold=True, center=True)

        for btn in self.opt_btns.values():
            btn.draw(surface)

    def _load_game(self):
        try:
            data = SaveSystem.load()
            if data:
                self.player = Player.from_dict(data['player'])
                # Load shop data if available
                shop_data = data.get('shop', None)
                self.shop = Shop.from_dict(SCREEN_W, SCREEN_H, shop_data) if shop_data else Shop(SCREEN_W, SCREEN_H)
                self.state = ST_CAMPFIRE
                self._build_campfire()
                self.campfire_hidden = True
                return
        except Exception as e:
            print(f'[Game] Failed to load save: {e}')

        self.state = ST_CHARGEN
        self._start_chargen()


# ── Convenience import shim ──────────────────────────────────
from src.items import Equipment
