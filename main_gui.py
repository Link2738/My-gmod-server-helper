"""
Gemboi's Gmod Server Helper GUI
A clean, modular, user-friendly tool for extracting .gma files, decompiling .mdl files, parsing QC bodygroups, and generating Pointshop Lua files.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Keep workshop_gen importable even when running from a different cwd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Work'))

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import threading
import json
import re
import shutil
from collections import defaultdict
from extractor import extract_gma, extract_vpk, extract_archive
from decompiler import decompile_mdl
from qc_parser import parse_qc_bodygroups, parse_qc_skins, parse_qc_type_signals, infer_type_from_qc, parse_qc_modelname, is_arms_stem, is_arms_qc, filter_npc_paths
from smd_parser import remove_weapon_bones_from_qc
from lua_writer import write_pointshop_lua, ensure_category_file, write_autorun_lua, _PM_TYPES
from config import load_last_paths, save_last_paths, load_custom_keywords, save_custom_keywords, load_cleaner_keywords, save_cleaner_keywords
from steamcmd_downloader import download_workshop_item, download_collection, detect_steam_path, find_workshop_in_steam
from vtf_resizer import read_vtf_dimensions, resize_vtf, clamp_dimensions
from resource_gen import generate_resource_file, merge_content_into_fastdl
from vmt_validator import scan_vmts, fix_vmts
from fastdl_checker import preflight
from smd_material_fixer import scan_decompiled, rewrite_smd_materials, clean_name, bad_names
from studiomdl_compiler import find_studiomdl, compile_qc, copy_mdl_to_addon, default_game_dir
from qc_parser import parse_qc_cdmaterials, rewrite_qc_texturegroup, rewrite_qc_cdmaterials, deduplicate_qc_animations, rewrite_qc_modelname

class GMAExtractorGUI:
    # ── Colour palette (Windows Aero) ──────────────────────────────────
    BG        = '#f0f0f0'
    FG        = '#1b1b1b'
    ACCENT    = '#0078d7'
    SURFACE   = '#ffffff'
    GREEN     = '#107c10'
    RED       = '#c42b1c'
    YELLOW    = '#ffb900'
    FONT      = ('Segoe UI', 10)
    FONT_BOLD = ('Segoe UI', 10, 'bold')
    FONT_HDR  = ('Segoe UI', 14, 'bold')

    # ── Supported games (display name → Steam App ID) ─────────────────
    GAMES = {
        'Garry\'s Mod':    '4000',
        'Left 4 Dead 2':   '550',
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Gemboi's Gmod Server Helper")
        self.root.minsize(720, 520)
        self.root.configure(bg=self.BG)
        self.style = ttk.Style()
        self.style.theme_use('vista')
        self.setup_vars()
        self.setup_widgets()
        self.abort_flag = {'abort': False}

    def setup_vars(self):
        last_type, last_paths, last_output, last_write_bodygroups, last_steamcmd, last_crowbar, last_game, last_steam, last_studiomdl, last_vtfcmd, last_max_tex_w, last_max_tex_h, last_model_namespace = load_last_paths()
        self.input_type = tk.StringVar(value=last_type)
        self.input_paths = dict(last_paths)           # per-type path memory
        self.input_path = tk.StringVar(value=self.input_paths.get(last_type, ''))
        self.output_dir = tk.StringVar(value=last_output)
        self.write_bodygroups = tk.BooleanVar(value=last_write_bodygroups)
        self.steamcmd_path = tk.StringVar(value=last_steamcmd)
        self.crowbarcli_path = tk.StringVar(value=last_crowbar)
        self.studiomdl_path = tk.StringVar(value=last_studiomdl or find_studiomdl(last_steam) or '')
        self.vtfcmd_path = tk.StringVar(value=last_vtfcmd)
        self.max_tex_w = tk.IntVar(value=last_max_tex_w)
        self.max_tex_h = tk.IntVar(value=last_max_tex_h)
        self.model_namespace = tk.StringVar(value=last_model_namespace)
        self.download_only = tk.BooleanVar(value=False)
        self.skip_lua = tk.BooleanVar(value=False)
        self.game_choice = tk.StringVar(value=last_game if last_game in self.GAMES else "Garry's Mod")
        self.steam_path = tk.StringVar(value=last_steam or detect_steam_path())
        self._switching_type = False                   # guard for trace callbacks
        self.custom_type_keywords = load_custom_keywords()
        self.cleaner_creator_keywords, self.cleaner_addon_keywords = load_cleaner_keywords()
        # Persist Addon Cleaner dialog state between openings
        self._cleaner_staging = ''
        self._cleaner_output  = ''
        self._cleaner_creator = ''
        self._cleaner_addon   = ''

    def _append_log(self, msg):
        """Centralized log append — used by all dialogs and workflows."""
        self.log_widget.config(state='normal')
        self.log_widget.insert('end', msg + '\n')
        self.log_widget.see('end')
        self.log_widget.config(state='disabled')
        self.root.update_idletasks()

    # ── Helpers ─────────────────────────────────────────────────────────
    def _frame(self, parent, **kw):
        bg = kw.pop('bg', self.BG)
        return tk.Frame(parent, bg=bg, **kw)

    def _label(self, parent, text, **kw):
        font = kw.pop('font', self.FONT)
        bg = kw.pop('bg', self.BG)
        fg = kw.pop('fg', self.FG)
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, **kw)

    def _entry(self, parent, textvariable, **kw):
        font = kw.pop('font', self.FONT)
        bg = kw.pop('bg', self.SURFACE)
        fg = kw.pop('fg', self.FG)
        insertbg = kw.pop('insertbackground', self.FG)
        relief = kw.pop('relief', 'solid')
        bd = kw.pop('bd', 1)
        return tk.Entry(parent, textvariable=textvariable,
                        bg=bg, fg=fg, insertbackground=insertbg,
                        font=font, relief=relief, bd=bd, **kw)

    def _button(self, parent, text, command, bg=None, fg=None, **kw):
        if bg:
            fg = fg or '#ffffff'
            font = kw.pop('font', self.FONT)
            relief = kw.pop('relief', 'raised')
            bd = kw.pop('bd', 1)
            padx = kw.pop('padx', 12)
            pady = kw.pop('pady', 3)
            cursor = kw.pop('cursor', 'hand2')
            activebg = kw.pop('activebackground', bg)
            activefg = kw.pop('activeforeground', fg)
            return tk.Button(parent, text=text, command=command,
                             bg=bg, fg=fg, activebackground=activebg,
                             activeforeground=activefg, font=font,
                             relief=relief, bd=bd, padx=padx, pady=pady,
                             cursor=cursor, **kw)
        return ttk.Button(parent, text=text, command=command, **kw)

    def _checkbox(self, parent, text, variable, **kw):
        return ttk.Checkbutton(parent, text=text, variable=variable, **kw)

    def _suggest_item_type(self, mdl_path, arms_path, qc_hint=None):
        path  = mdl_path.replace('\\', '/').lower()
        parts = path.split('/')
        stem  = os.path.splitext(parts[-1])[0]

        _BEAR_KW = {'bear', 'ursa', 'ursid', 'panda', 'grizzly', 'polar', 'kodiak', 'cub'}

        # Custom user-defined keywords — highest priority
        for kw, type_key in self.custom_type_keywords.items():
            kw = kw.lower()
            if kw in stem or any(kw in p for p in parts):
                return type_key

        # QC structural inference — authoritative when available
        if qc_hint == 'swep':
            return 'swep'
        if qc_hint == 'accessory':
            return 'accessory'
        if qc_hint == 'playermodel':
            if any(kw in stem or any(kw in p for p in parts) for kw in _BEAR_KW):
                return 'bear_playermodel'
            return 'victim_playermodel'

        # Path/stem heuristics — fallback when QC is inconclusive
        _SWEP_PATH = {'weapons', 'weapon', 'sweps'}
        _SWEP_STEM = ('w_', 'c_', 'weapon_', '_swep')
        if any(p in _SWEP_PATH for p in parts):
            return 'swep'
        if any(stem.startswith(k) or stem.endswith(k.rstrip('_')) for k in _SWEP_STEM):
            return 'swep'

        _ACC_PATH = {'props', 'accessories', 'hats', 'props_accessories', 'wearables'}
        _ACC_STEM = ('hat_', '_hat', 'acc_', '_acc', 'mask_', 'helm_', 'cap_', 'crown_', 'wig_')
        if any(p in _ACC_PATH for p in parts):
            return 'accessory'
        if any(stem.startswith(k) or stem.endswith(k.rstrip('_')) for k in _ACC_STEM):
            return 'accessory'

        if any(kw in stem or any(kw in p for p in parts) for kw in _BEAR_KW):
            return 'bear_playermodel'

        return 'victim_playermodel'

    # ── Main layout ───────────────────────────────────────────────────
    def setup_widgets(self):
        # ── Menu Bar ─────────────────────────────────────────────────
        menubar = tk.Menu(self.root, bg=self.SURFACE, fg=self.FG)
        self.root.config(menu=menubar)

        tools_menu = tk.Menu(menubar, tearoff=0, bg=self.SURFACE, fg=self.FG)
        menubar.add_cascade(label='Tools', menu=tools_menu)
        tools_menu.add_command(label='Patch FastDL', command=self.patch_fastdl)
        tools_menu.add_command(label='Generate FastDL resource.lua', command=self.generate_resource_lua)
        tools_menu.add_command(label='Validate VMTs...', command=self.validate_vmts)
        tools_menu.add_command(label='FastDL Pre-flight Check...', command=self.fastdl_preflight)
        tools_menu.add_command(label='Fix Material Names...', command=self.fix_material_names)
        tools_menu.add_command(label='Addon Cleaner...', command=self.clean_addon)
        tools_menu.add_command(label='Generate workshop_content.lua',
                               command=self.generate_workshop_lua, state='disabled')
        self._tools_menu = tools_menu
        self._workshop_menu_idx = tools_menu.index('end')

        help_menu = tk.Menu(menubar, tearoff=0, bg=self.SURFACE, fg=self.FG)
        menubar.add_cascade(label='Help', menu=help_menu)
        help_menu.add_command(label='Instructions', command=self._show_instructions)
        help_menu.add_command(label='About', command=lambda: messagebox.showinfo(
            'About', "Gemboi's Gmod Server Helper\n"
                     "Batch-processes GMod player models into PointShop Lua files.\n\n"
                     "Supported: .gma, .bin, .vpk, .mdl, Workshop, Collections."))

        pad = {'padx': 14, 'pady': 2}
        outer = self._frame(self.root)
        outer.pack(fill='both', expand=True, padx=6, pady=6)

        # ── Header row (title + config) ──────────────────────────────
        hdr = self._frame(outer)
        hdr.pack(fill='x', padx=14, pady=(6, 4))
        tk.Label(hdr, text="Gemboi's Gmod Server Helper",
                 bg=self.BG, fg=self.ACCENT, font=self.FONT_HDR).pack(side='left')
        self._button(hdr, "\u2699  Config", self.open_config_popup).pack(side='right')

        # \u2500\u2500 Setup health bar \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        health_row = self._frame(outer)
        health_row.pack(fill='x', padx=14, pady=(0, 2))
        self._dot_steamcmd = tk.Label(health_row, text='\u25cf', bg=self.BG, font=self.FONT)
        self._dot_steamcmd.pack(side='left')
        self._label(health_row, 'SteamCMD', fg='#666666').pack(side='left', padx=(3, 14))
        self._dot_crowbar = tk.Label(health_row, text='\u25cf', bg=self.BG, font=self.FONT)
        self._dot_crowbar.pack(side='left')
        self._label(health_row, 'CrowbarCLI', fg='#666666').pack(side='left', padx=(3, 14))
        self._dot_output = tk.Label(health_row, text='\u25cf', bg=self.BG, font=self.FONT)
        self._dot_output.pack(side='left')
        self._label(health_row, 'Output folder', fg='#666666').pack(side='left', padx=(3, 14))
        self._dot_studiomdl = tk.Label(health_row, text='\u25cf', bg=self.BG, font=self.FONT)
        self._dot_studiomdl.pack(side='left')
        self._label(health_row, 'studiomdl', fg='#666666').pack(side='left', padx=(3, 14))
        self._dot_vtfcmd = tk.Label(health_row, text='\u25cf', bg=self.BG, font=self.FONT)
        self._dot_vtfcmd.pack(side='left')
        self._label(health_row, 'VTFCmd', fg='#666666').pack(side='left', padx=(3, 0))

        # \u2500\u2500 First-run banner (shown if tools not configured) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        self._banner_frame = self._frame(outer, bg='#fff3cd')
        tk.Label(self._banner_frame,
                 text='\u26a0  First time? Open Config (top-right) to set required tool paths before processing.',
                 bg='#fff3cd', fg='#856404', font=self.FONT, anchor='w'
                 ).pack(side='left', padx=(10, 0), pady=4, fill='x', expand=True)
        tk.Button(self._banner_frame, text='\u2715', bg='#fff3cd', fg='#856404',
                  relief='flat', font=self.FONT, cursor='hand2',
                  command=self._banner_frame.pack_forget).pack(side='right', padx=6)

        # ── Input section ────────────────────────────────────────────
        input_frame = self._frame(outer)
        input_frame.pack(fill='x', **pad)

        self._label(input_frame, "Input:").pack(side='left')
        type_combo = ttk.Combobox(input_frame, textvariable=self.input_type,
                                  values=['File', 'Folder', 'Workshop', 'Collection'],
                                  state='readonly', width=10, font=self.FONT)
        type_combo.pack(side='left', padx=(4, 8))

        game_combo = ttk.Combobox(input_frame, textvariable=self.game_choice,
                                  values=list(self.GAMES.keys()),
                                  state='readonly', width=18, font=self.FONT)
        game_combo.pack(side='left', padx=(0, 8))

        self._entry(input_frame, self.input_path, width=48).pack(side='left', fill='x', expand=True)
        self._button(input_frame, "Browse", self.browse_input).pack(side='left', padx=(6, 0))

        # ── Contextual input-type help ────────────────────────────────
        self._type_help_label = self._label(outer, '', fg='#666666',
                                            font=('Segoe UI', 9, 'italic'))
        self._type_help_label.pack(fill='x', padx=18, pady=(0, 2))

        # ── Output section ───────────────────────────────────────────
        out_frame = self._frame(outer)
        out_frame.pack(fill='x', **pad)

        self._label(out_frame, "Output:").pack(side='left')
        self._entry(out_frame, self.output_dir, width=55).pack(side='left', padx=(4, 0), fill='x', expand=True)
        self._button(out_frame, "Browse", self.browse_output).pack(side='left', padx=(6, 0))

        # ── Per-type path swap on type change ────────────────────────
        _TYPE_HELP = {
            'File':       'Browse for a .gma, .bin, .vpk, or .mdl file.',
            'Folder':     'Select a folder — extracts all addon files and .mdl files found inside.',
            'Workshop':   'Enter a Workshop ID or URL — requires SteamCMD to be configured.',
            'Collection': 'Enter a Collection ID or URL — downloads and processes all items in the collection.',
        }

        def _on_type_change(*_args):
            """Store the current path, then restore the path for the new type."""
            self._switching_type = True
            new_type = self.input_type.get()
            # Save whatever was in the entry for the *previous* type
            for t, v in self.input_paths.items():
                pass  # just need the dict alive
            # (current entry text belongs to the previous type — already
            #  captured by _on_path_change below before combobox fires)
            # Load the stored path for the newly selected type
            self.input_path.set(self.input_paths.get(new_type, ''))
            self._switching_type = False
            _persist()
            self._type_help_label.config(text=_TYPE_HELP.get(new_type, ''))

        def _on_path_change(*_args):
            """Keep the per-type dict in sync as the user edits the entry."""
            if self._switching_type:
                return
            self.input_paths[self.input_type.get()] = self.input_path.get()
            _persist()

        def _persist(*_args):
            self.input_paths[self.input_type.get()] = self.input_path.get()
            save_last_paths(
                self.input_type.get(), self.input_paths,
                self.output_dir.get(), self.write_bodygroups.get(),
                self.steamcmd_path.get(), self.crowbarcli_path.get(),
                self.game_choice.get(), self.steam_path.get())

        self.input_type.trace_add('write', _on_type_change)
        self.input_path.trace_add('write', _on_path_change)
        self.output_dir.trace_add('write', _persist)
        self.game_choice.trace_add('write', _persist)

        # ── Options ──────────────────────────────────────────────────
        sep = ttk.Separator(outer, orient='horizontal')
        sep.pack(fill='x', padx=14, pady=(6, 2))

        opts = self._frame(outer)
        opts.pack(fill='x', **pad)

        self.write_bodygroups_chk = self._checkbox(
            opts, "Write bodygroups & skins",
            self.write_bodygroups)
        self.write_bodygroups_chk.pack(side='left', padx=(0, 16))

        self.download_only_chk = self._checkbox(
            opts, "Download only (skip extraction)",
            self.download_only)
        self.download_only_chk.pack(side='left', padx=(0, 16))

        self.skip_lua_chk = self._checkbox(
            opts, "Skip Lua generation",
            self.skip_lua)
        self.skip_lua_chk.pack(side='left')

        # ── Console log ──────────────────────────────────────────────
        sep2 = ttk.Separator(outer, orient='horizontal')
        sep2.pack(fill='x', padx=14, pady=(6, 2))

        self.log_widget = scrolledtext.ScrolledText(
            outer, height=14, bg='#1e1e1e', fg='#cccccc',
            insertbackground='#cccccc', font=('Consolas', 9),
            relief='solid', bd=1, wrap='word')
        self.log_widget.pack(fill='both', expand=True, padx=14, pady=(4, 6))

        # ── Action buttons ───────────────────────────────────────────
        btn_bar = self._frame(outer)
        btn_bar.pack(fill='x', padx=14, pady=(0, 8))

        self._button(btn_bar, "Copy Log", self.copy_console_output).pack(side='left')

        self._button(btn_bar, "Abort", self.abort_process,
                     bg=self.RED, fg='#ffffff').pack(side='right', padx=(6, 0))
        self.process_button = self._button(
            btn_bar, "Extract && Generate Lua", self.start_process,
            bg=self.GREEN, fg='#ffffff')
        self.process_button.pack(side='right')

        # ── Dynamic state for download-only checkbox ─────────────────
        def update_download_only_state(*_args):
            if self.input_type.get() in ('Workshop', 'Collection'):
                self.download_only_chk.config(state='normal')
            else:
                self.download_only_chk.config(state='disabled')
                self.download_only.set(False)
            # workshop_content.lua menu item only makes sense for Collection
            new_state = 'normal' if self.input_type.get() == 'Collection' else 'disabled'
            self._tools_menu.entryconfig(self._workshop_menu_idx, state=new_state)
        self.input_type.trace_add('write', update_download_only_state)

        # ── Initial state ─────────────────────────────────────────────
        self._type_help_label.config(text=_TYPE_HELP.get(self.input_type.get(), ''))
        self.steamcmd_path.trace_add('write', lambda *_: self._update_health_bar())
        self.crowbarcli_path.trace_add('write', lambda *_: self._update_health_bar())
        self.output_dir.trace_add('write', lambda *_: self._update_health_bar())
        self.studiomdl_path.trace_add('write', lambda *_: self._update_health_bar())
        self._update_health_bar()
        if not (self.steamcmd_path.get() and os.path.isfile(self.steamcmd_path.get())) \
                or not (self.crowbarcli_path.get() and os.path.isfile(self.crowbarcli_path.get())):
            self._banner_frame.pack(fill='x', padx=14, pady=(0, 4))
        update_download_only_state()

    def patch_fastdl(self):
        """
        Two-part FastDL patch dialog:
          1. Copy a local folder of edited content (models/, materials/, etc.) into
             an existing fastdl/ directory, overwriting matched files.
          2. View and hand-edit the resource.AddFile() Lua file in a text area.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Patch FastDL")
        dlg.geometry("720x620")
        dlg.configure(bg=self.BG)
        dlg.transient(self.root)
        dlg.resizable(True, True)

        # ── Path rows ────────────────────────────────────────────────
        def path_row(parent, label, initial=''):
            f = self._frame(parent)
            f.pack(fill='x', padx=14, pady=(6, 2))
            self._label(f, label).pack(side='left')
            var = tk.StringVar(value=initial)
            self._entry(f, var).pack(side='left', padx=(6, 0), fill='x', expand=True)
            def browse_dir():
                d = filedialog.askdirectory()
                if d:
                    var.set(d)
            self._button(f, "Browse", browse_dir).pack(side='left', padx=(6, 0))
            return var

        def path_row_file(parent, label, filetypes, initial=''):
            f = self._frame(parent)
            f.pack(fill='x', padx=14, pady=(6, 2))
            self._label(f, label).pack(side='left')
            var = tk.StringVar(value=initial)
            self._entry(f, var).pack(side='left', padx=(6, 0), fill='x', expand=True)
            def browse_file():
                p = filedialog.askopenfilename(filetypes=filetypes)
                if p:
                    var.set(p)
            self._button(f, "Browse", browse_file).pack(side='left', padx=(6, 0))
            return var

        # Default: guess fastdl/ folder from current output dir
        default_fastdl = ''
        if self.output_dir.get():
            candidate = os.path.join(self.output_dir.get(), 'fastdl')
            if os.path.isdir(candidate):
                default_fastdl = candidate

        # Default lua path
        default_lua = ''
        if self.output_dir.get():
            candidate = os.path.join(self.output_dir.get(), 'lua', 'autorun', 'server',
                                     'resource_fastdl_content.lua')
            if os.path.isfile(candidate):
                default_lua = candidate

        fastdl_var = path_row(dlg, 'FastDL folder: ', default_fastdl)
        patch_var  = path_row(dlg, 'Patch folder:  ')
        lua_var    = path_row_file(dlg, 'Resource lua:  ',
                                   [('Lua files', '*.lua'), ('All files', '*.*')],
                                   default_lua)

        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))

        # ── Log ───────────────────────────────────────────────────────
        log_area = scrolledtext.ScrolledText(
            dlg, height=6, bg='#1e1e1e', fg='#cccccc',
            insertbackground='#cccccc', font=('Consolas', 9),
            relief='solid', bd=1, wrap='word')
        log_area.pack(fill='x', padx=14, pady=(2, 4))

        def dlog(msg):
            log_area.insert('end', msg + '\n')
            log_area.see('end')
            log_area.update_idletasks()

        # ── Copy patched files ────────────────────────────────────────
        def do_patch():
            patch_dir  = patch_var.get().strip()
            fastdl_dir = fastdl_var.get().strip()
            if not patch_dir or not os.path.isdir(patch_dir):
                dlog('[ERROR] Patch folder is empty or does not exist.')
                return
            if not fastdl_dir or not os.path.isdir(fastdl_dir):
                dlog('[ERROR] FastDL folder is empty or does not exist.')
                return

            def run():
                import shutil
                copied = overwritten = 0
                for dirpath, _dirs, filenames in os.walk(patch_dir):
                    for fname in filenames:
                        src = os.path.join(dirpath, fname)
                        rel = os.path.relpath(src, patch_dir)
                        dst = os.path.join(fastdl_dir, rel)
                        is_new = not os.path.exists(dst)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                        if is_new:
                            copied += 1
                            dlog(f'[COPY]  {rel}')
                        else:
                            overwritten += 1
                            dlog(f'[OVER]  {rel}')
                dlog(f'[DONE] {copied} new, {overwritten} overwritten.')

            threading.Thread(target=run, daemon=True).start()

        # ── Regenerate lua from fastdl folder ─────────────────────────
        def do_rescan():
            fastdl_dir = fastdl_var.get().strip()
            lua_path   = lua_var.get().strip()
            if not fastdl_dir or not os.path.isdir(fastdl_dir):
                dlog('[ERROR] FastDL folder is empty or does not exist.')
                return
            if not lua_path:
                # Default placement
                lua_path = os.path.join(self.output_dir.get() or fastdl_dir,
                                        'lua', 'autorun', 'server',
                                        'resource_fastdl_content.lua')
                lua_var.set(lua_path)

            def run():
                from resource_gen import scan_content_files, write_resource_lua
                file_list = scan_content_files(fastdl_dir, dlog)
                if not file_list:
                    dlog('[WARN] No content files found in FastDL folder.')
                    return
                write_resource_lua(file_list, lua_path,
                                   addon_name='fastdl_content', log_callback=dlog)
                dlog(f'[DONE] Lua written: {lua_path}')
                # Refresh text editor
                dlg.after(0, load_lua_into_editor)

            threading.Thread(target=run, daemon=True).start()

        # ── Button row ────────────────────────────────────────────────
        btn_row = self._frame(dlg)
        btn_row.pack(fill='x', padx=14, pady=(0, 4))
        self._button(btn_row, 'Copy Patch Files → FastDL', do_patch,
                     bg=self.ACCENT, fg='#ffffff').pack(side='left')
        self._button(btn_row, 'Re-scan & Regenerate Lua', do_rescan
                     ).pack(side='left', padx=(8, 0))

        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(4, 2))

        # ── Lua text editor ───────────────────────────────────────────
        self._label(dlg, 'resource.lua editor:', font=self.FONT).pack(
            anchor='w', padx=14)
        lua_editor = scrolledtext.ScrolledText(
            dlg, bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='#d4d4d4', font=('Consolas', 9),
            relief='solid', bd=1, wrap='none')
        lua_editor.pack(fill='both', expand=True, padx=14, pady=(2, 4))

        def load_lua_into_editor():
            p = lua_var.get().strip()
            if p and os.path.isfile(p):
                with open(p, 'r', encoding='utf-8') as f:
                    content = f.read()
                lua_editor.delete('1.0', 'end')
                lua_editor.insert('1.0', content)

        def save_lua_from_editor():
            p = lua_var.get().strip()
            if not p:
                dlog('[ERROR] No Lua file path set.')
                return
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(lua_editor.get('1.0', 'end-1c'))
            dlog(f'[SAVED] {p}')

        # Auto-load if a default lua was found
        if default_lua:
            load_lua_into_editor()

        # Reload editor when lua path changes
        lua_var.trace_add('write', lambda *_: load_lua_into_editor())

        # Save button pinned at bottom
        save_row = self._frame(dlg)
        save_row.pack(fill='x', padx=14, pady=(0, 10))
        self._button(save_row, 'Save Lua', save_lua_from_editor,
                     bg=self.GREEN, fg='#ffffff').pack(side='left')
        self._button(save_row, 'Close', dlg.destroy).pack(side='right')

    def generate_resource_lua(self):
        """Open the FastDL collection generator dialog."""
        dlg = tk.Toplevel(self.root)
        dlg.title("FastDL Collection Generator")
        dlg.geometry("640x560")
        dlg.configure(bg=self.BG)
        dlg.transient(self.root)
        dlg.resizable(True, True)

        # ── Source mode toggle ────────────────────────────────────────
        mode_var = tk.StringVar(value='collection')
        mode_row = self._frame(dlg)
        mode_row.pack(fill='x', padx=14, pady=(12, 4))
        self._label(mode_row, 'Source:').pack(side='left')
        tk.Radiobutton(mode_row, text='Workshop Collection', variable=mode_var,
                       value='collection', bg=self.BG, fg=self.FG,
                       activebackground=self.BG, font=self.FONT,
                       command=lambda: _toggle_mode()).pack(side='left', padx=(8, 0))
        tk.Radiobutton(mode_row, text='Local Folder', variable=mode_var,
                       value='folder', bg=self.BG, fg=self.FG,
                       activebackground=self.BG, font=self.FONT,
                       command=lambda: _toggle_mode()).pack(side='left', padx=(8, 0))

        # ── Collection ID (collection mode) ──────────────────────────
        coll_row = self._frame(dlg)
        coll_row.pack(fill='x', padx=14, pady=(2, 2))
        self._label(coll_row, 'Collection ID/URL:').pack(side='left')
        initial_id = self.input_path.get() if self.input_type.get() == 'Collection' else ''
        collection_var = tk.StringVar(value=initial_id)
        self._entry(coll_row, collection_var, width=38).pack(side='left', padx=(6, 0), fill='x', expand=True)

        # ── Content folder (folder mode, hidden initially) ────────────
        folder_row = self._frame(dlg)
        self._label(folder_row, 'Content folder:   ').pack(side='left')
        content_folder_var = tk.StringVar(value='')
        self._entry(folder_row, content_folder_var, width=38).pack(side='left', padx=(6, 0), fill='x', expand=True)
        def _browse_content():
            d = filedialog.askdirectory(title='Select local content folder to scan')
            if d:
                content_folder_var.set(d)
        self._button(folder_row, 'Browse', _browse_content).pack(side='left', padx=(6, 0))

        def _toggle_mode():
            if mode_var.get() == 'collection':
                folder_row.pack_forget()
                coll_row.pack(fill='x', padx=14, pady=(2, 2))
            else:
                coll_row.pack_forget()
                folder_row.pack(fill='x', padx=14, pady=(2, 2))

        # ── Output folder ────────────────────────────────────────────
        row2 = self._frame(dlg)
        row2.pack(fill='x', padx=14, pady=(2, 4))
        self._label(row2, 'Output folder:   ').pack(side='left')
        out_var = tk.StringVar(value=self.output_dir.get())
        self._entry(row2, out_var, width=38).pack(side='left', padx=(6, 0), fill='x', expand=True)
        def _browse_out():
            d = filedialog.askdirectory(title='Select Output Folder')
            if d:
                out_var.set(d)
        self._button(row2, 'Browse', _browse_out).pack(side='left', padx=(6, 0))

        # ── Log area ─────────────────────────────────────────────────
        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(4, 2))
        log_area = scrolledtext.ScrolledText(
            dlg, height=18, bg='#1e1e1e', fg='#cccccc',
            insertbackground='#cccccc', font=('Consolas', 9),
            relief='solid', bd=1, wrap='word')
        log_area.pack(fill='both', expand=True, padx=14, pady=(2, 4))

        def dlog(msg):
            log_area.insert('end', msg + '\n')
            log_area.see('end')
            log_area.update_idletasks()

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = self._frame(dlg)
        btn_row.pack(fill='x', padx=14, pady=(0, 10))
        gen_btn = self._button(btn_row, 'Generate FastDL', None,
                               bg=self.GREEN, fg='#ffffff')
        gen_btn.pack(side='left')
        self._button(btn_row, 'Close', dlg.destroy).pack(side='right')

        def run_fastdl():
            gen_btn.config(state='disabled')
            mode       = mode_var.get()
            output_dir = out_var.get().strip()

            if not output_dir:
                dlog('[ERROR] No output folder selected.')
                gen_btn.config(state='normal')
                return

            if mode == 'folder':
                # ── Local folder mode: scan directly, no Steam download ──
                content_folder = content_folder_var.get().strip()
                if not content_folder or not os.path.isdir(content_folder):
                    dlog('[ERROR] No valid content folder selected.')
                    gen_btn.config(state='normal')
                    return

                def run_folder():
                    try:
                        dlog(f'[INFO] ══ Scanning folder: {content_folder} ══')
                        lua_path = generate_resource_file(
                            content_folder, output_dir,
                            addon_name='fastdl_content', log_callback=dlog)
                        dlog('')
                        dlog('[DONE] ══════════════════════════════════════')
                        if lua_path:
                            dlog(f'[DONE] Resource Lua: {lua_path}')
                        dlog('[DONE] ══════════════════════════════════════')
                        dlog('[INFO] Add the resource Lua to your server\'s lua/autorun/server/.')
                    except Exception as e:
                        import traceback
                        dlog(f'[ERROR] {e}')
                        dlog(traceback.format_exc())
                    finally:
                        dlg.after(0, lambda: gen_btn.config(state='normal'))

                threading.Thread(target=run_folder, daemon=True).start()
                return

            # ── Collection mode: download → extract → merge → lua ────
            collection_raw = collection_var.get().strip()
            steamcmd_path  = self.steamcmd_path.get().strip()

            if not collection_raw:
                dlog('[ERROR] No collection ID or URL entered.')
                gen_btn.config(state='normal')
                return
            if not steamcmd_path or not os.path.isfile(steamcmd_path):
                dlog('[ERROR] SteamCMD path not set or invalid. Set it in Config > SteamCMD first.')
                gen_btn.config(state='normal')
                return

            if 'id=' in collection_raw:
                collection_id = collection_raw.split('id=')[-1].split('&')[0].strip()
            else:
                collection_id = collection_raw

            def run():
                try:
                    dlog(f'[INFO] ══ Downloading collection {collection_id} ══')
                    gma_files = download_collection(
                        steamcmd_path, collection_id, output_dir, dlog)
                    if not gma_files:
                        dlog('[ERROR] No files downloaded — check the collection ID and SteamCMD.')
                        return
                    dlog(f'[INFO] Downloaded {len(gma_files)} archive(s).')

                    extracted_dir = os.path.join(output_dir, 'fastdl_raw')
                    dlog(f'[INFO] ══ Extracting archives ══')
                    for gma_file in gma_files:
                        addon_name = os.path.splitext(os.path.basename(gma_file))[0]
                        extract_to = os.path.join(extracted_dir, addon_name)
                        os.makedirs(extract_to, exist_ok=True)
                        extract_archive(gma_file, extract_to, dlog)

                    fastdl_dir = output_dir
                    dlog(f'[INFO] ══ Merging content into output folder ══')
                    count = merge_content_into_fastdl(extracted_dir, fastdl_dir, dlog)
                    if count == 0:
                        dlog('[WARN] No downloadable content files found after extraction.')
                        return

                    dlog(f'[INFO] ══ Writing resource.lua ══')
                    lua_path = generate_resource_file(
                        fastdl_dir, output_dir,
                        addon_name='fastdl_content', log_callback=dlog)

                    dlog('')
                    dlog('[DONE] ══════════════════════════════════════')
                    dlog(f'[DONE] FastDL content folder:  {fastdl_dir}')
                    if lua_path:
                        dlog(f'[DONE] Resource Lua:           {lua_path}')
                    dlog('[DONE] ══════════════════════════════════════')
                    dlog('[INFO] Upload the contents of this folder to your web host root.')
                    dlog('[INFO] Add the resource Lua to your server\'s lua/autorun/server/.')
                except Exception as e:
                    import traceback
                    dlog(f'[ERROR] {e}')
                    dlog(traceback.format_exc())
                finally:
                    dlg.after(0, lambda: gen_btn.config(state='normal'))

            threading.Thread(target=run, daemon=True).start()

        gen_btn.config(command=run_fastdl)

    def validate_vmts(self):
        """Scan a folder for .vmt issues, then offer to auto-fix what's fixable."""
        start_dir = self.output_dir.get() or os.getcwd()
        folder = filedialog.askdirectory(
            title='Select folder to scan for .vmt files',
            initialdir=start_dir,
        )
        if not folder:
            return

        def run():
            self._append_log(f'\n[VMT] Scanning: {folder}')
            total, bad = scan_vmts(folder, log_callback=self._append_log)
            if not bad:
                self._append_log(f'[VMT] All {total} file(s) OK — no issues found.')
                return

            self._append_log(f'[VMT] {len(bad)} file(s) with issues out of {total} scanned.')

            # Offer to fix from the main thread (messagebox requires it)
            event = threading.Event()
            answer = [False]
            def _ask():
                answer[0] = messagebox.askyesno(
                    'Fix VMTs?',
                    f'{len(bad)} file(s) have issues.\n\n'
                    'Auto-fix can repair truncated files (missing closing braces) '
                    'and strip null bytes.\n\n'
                    'Files with structural corruption will be skipped.\n\n'
                    'Attempt auto-fix now?',
                )
                event.set()
            self.root.after(0, _ask)
            event.wait()

            if not answer[0]:
                self._append_log('[VMT] Fix skipped.')
                return

            self._append_log('[VMT] Attempting fixes...')
            fixed, skipped = fix_vmts(folder, bad, log_callback=self._append_log)
            self._append_log(f'[VMT] Done — {fixed} fixed, {skipped} skipped (manual review needed).')

        threading.Thread(target=run, daemon=True).start()

    def fastdl_preflight(self):
        """Run path + VMT checks on a FastDL content folder and report all issues."""
        start_dir = self.output_dir.get() or os.getcwd()
        folder = filedialog.askdirectory(
            title='Select FastDL content folder to check',
            initialdir=start_dir,
        )
        if not folder:
            return

        def run():
            self._append_log(f'\n[PRE-FLIGHT] Scanning: {folder}')
            results = preflight(folder, log_callback=self._append_log)
            path_issues = results['path_issues']
            vmt_bad     = results['vmt_bad']
            vmt_total   = results['vmt_total']

            self._append_log(f'[PRE-FLIGHT] Done — {len(path_issues)} path issue(s), '
                f'{len(vmt_bad)} VMT issue(s) in {vmt_total} file(s) scanned.')

            if path_issues:
                self._append_log('[PRE-FLIGHT] Path issues must be fixed manually '
                    '(rename or remove the offending files).')

            if not vmt_bad:
                return

            event = threading.Event()
            answer = [False]
            def _ask():
                answer[0] = messagebox.askyesno(
                    'Fix VMT Errors?',
                    f'{len(vmt_bad)} VMT file(s) have structural errors.\n\n'
                    'Auto-fix can repair truncated files and strip null bytes.\n'
                    'Structurally corrupted files will be skipped.\n\n'
                    'Attempt auto-fix now?',
                )
                event.set()
            self.root.after(0, _ask)
            event.wait()

            if not answer[0]:
                return
            self._append_log('[PRE-FLIGHT] Fixing VMTs...')
            fixed, skipped = fix_vmts(folder, vmt_bad, log_callback=self._append_log)
            self._append_log(f'[PRE-FLIGHT] {fixed} fixed, {skipped} skipped (manual review needed).')

        threading.Thread(target=run, daemon=True).start()

    def generate_workshop_lua(self):
        collection_id = self.input_path.get().strip()
        if not collection_id:
            messagebox.showwarning("No Collection ID", "Enter a collection ID or URL in the Input field first.")
            return
        if "id=" in collection_id:
            collection_id = collection_id.split("id=")[-1].split("&")[0]

        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning("No Output", "Select an output directory first.")
            return

        def run():
            from workshop_gen import fetch_collection, fetch_item_names, write_lua

            try:
                self._append_log(f'[INFO] Fetching collection {collection_id}...')
                children = fetch_collection(collection_id)
                file_ids = [c['publishedfileid'] for c in children if 'publishedfileid' in c]
                self._append_log(f'[INFO] Found {len(file_ids)} item(s). Fetching names...')
                names = fetch_item_names(file_ids)
                out_path = os.path.join(output_dir, 'workshop_content.lua')
                write_lua(children, names, out_path)
                self._append_log(f'[SUCCESS] Written to: {out_path}')
            except Exception as e:
                self._append_log(f'[ERROR] {e}')

        threading.Thread(target=run, daemon=True).start()

    def open_config_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Configuration")
        popup.geometry("520x320")
        popup.configure(bg=self.BG)
        popup.transient(self.root)
        popup.grab_set()

        # Always reload config from disk for latest values
        config_path = os.path.join('config', 'last_paths.json')
        steamcmd_val = self.steamcmd_path.get()
        crowbar_val = self.crowbarcli_path.get()
        steam_val = self.steam_path.get()
        namespace_val = self.model_namespace.get()
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                steamcmd_val = data.get('steamcmd_path', steamcmd_val)
                crowbar_val = data.get('crowbarcli_path', crowbar_val)
                steam_val = data.get('steam_path', steam_val)
                namespace_val = data.get('model_namespace', namespace_val)
            except Exception:
                pass

        body = self._frame(popup)
        body.pack(fill='both', expand=True, padx=14, pady=10)

        # ── SteamCMD row ─────────────────────────────────────────────
        self._label(body, "SteamCMD path:").grid(row=0, column=0, sticky='w', pady=(0, 4))
        steamcmd_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                                  insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        steamcmd_entry.grid(row=0, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        steamcmd_entry.insert(0, steamcmd_val)

        def browse_steamcmd():
            path = filedialog.askopenfilename(title="Select steamcmd executable",
                                              filetypes=[("SteamCMD Executable", "steamcmd.exe")])
            if path:
                steamcmd_entry.delete(0, tk.END)
                steamcmd_entry.insert(0, path)
                update_config()

        self._button(body, "Browse", browse_steamcmd).grid(row=0, column=2, pady=(0, 4))

        # ── CrowbarCLI row ───────────────────────────────────────────
        self._label(body, "CrowbarCLI path:").grid(row=1, column=0, sticky='w', pady=(0, 4))
        crowbar_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                                 insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        crowbar_entry.grid(row=1, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        crowbar_entry.insert(0, crowbar_val)

        def browse_crowbar():
            path = filedialog.askopenfilename(
                title="Select crowbarcli executable",
                filetypes=[
                    ("CrowbarCommandLineDecomp", "CrowbarCommandLineDecomp.exe"),
                    ("CrowbarCLI Executable", "crowbarcli.exe"),
                ])
            if path:
                crowbar_entry.delete(0, tk.END)
                crowbar_entry.insert(0, path)
                update_config()

        self._button(body, "Browse", browse_crowbar).grid(row=1, column=2, pady=(0, 4))

        # ── Steam path row (for non-GMod workshop lookups) ───────────
        self._label(body, "Steam path:").grid(row=2, column=0, sticky='w', pady=(0, 4))
        steam_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                               insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        steam_entry.grid(row=2, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        steam_entry.insert(0, steam_val)

        def browse_steam():
            path = filedialog.askdirectory(title="Select Steam installation folder")
            if path:
                steam_entry.delete(0, tk.END)
                steam_entry.insert(0, path)
                update_config()

        self._button(body, "Browse", browse_steam).grid(row=2, column=2, pady=(0, 4))

        # ── studiomdl row ─────────────────────────────────────────────
        self._label(body, "studiomdl path:").grid(row=3, column=0, sticky='w', pady=(0, 4))
        studiomdl_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                                   insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        studiomdl_entry.grid(row=3, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        studiomdl_entry.insert(0, self.studiomdl_path.get())

        def browse_studiomdl():
            path = filedialog.askopenfilename(
                title="Select studiomdl.exe",
                filetypes=[("studiomdl", "studiomdl.exe"), ("All executables", "*.exe")])
            if path:
                studiomdl_entry.delete(0, tk.END)
                studiomdl_entry.insert(0, path)
                update_config()

        self._button(body, "Browse", browse_studiomdl).grid(row=3, column=2, pady=(0, 4))

        # ── VTFCmd row ────────────────────────────────────────────────
        self._label(body, "VTFCmd path:").grid(row=4, column=0, sticky='w', pady=(0, 4))
        vtfcmd_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                                insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        vtfcmd_entry.grid(row=4, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        vtfcmd_entry.insert(0, self.vtfcmd_path.get())

        def browse_vtfcmd():
            path = filedialog.askopenfilename(
                title="Select VTFCmd.exe",
                filetypes=[("VTFCmd", "VTFCmd.exe"), ("All executables", "*.exe")])
            if path:
                vtfcmd_entry.delete(0, tk.END)
                vtfcmd_entry.insert(0, path)
                update_config()

        self._button(body, "Browse", browse_vtfcmd).grid(row=4, column=2, pady=(0, 4))

        # ── Model Namespace row ────────────────────────────────────────
        self._label(body, "Model Namespace:").grid(row=5, column=0, sticky='w', pady=(0, 4))
        namespace_entry = tk.Entry(body, width=48, bg=self.SURFACE, fg=self.FG,
                                   insertbackground=self.FG, font=self.FONT, relief='solid', bd=1)
        namespace_entry.grid(row=5, column=1, sticky='ew', padx=(6, 4), pady=(0, 4))
        namespace_entry.insert(0, namespace_val)

        body.columnconfigure(1, weight=1)

        def update_config():
            try:
                self.input_paths[self.input_type.get()] = self.input_path.get()
                save_last_paths(
                    self.input_type.get(), self.input_paths,
                    self.output_dir.get(), self.write_bodygroups.get(),
                    steamcmd_entry.get(), crowbar_entry.get(),
                    self.game_choice.get(), steam_entry.get(),
                    studiomdl_entry.get(), vtfcmd_entry.get(),
                    self.max_tex_w.get(), self.max_tex_h.get(),
                    namespace_entry.get())
                self.steamcmd_path.set(steamcmd_entry.get())
                self.crowbarcli_path.set(crowbar_entry.get())
                self.steam_path.set(steam_entry.get())
                self.studiomdl_path.set(studiomdl_entry.get())
                self.vtfcmd_path.set(vtfcmd_entry.get())
                self.model_namespace.set(namespace_entry.get())
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

        # Save on focus-out
        steamcmd_entry.bind('<FocusOut>', lambda _: update_config())
        crowbar_entry.bind('<FocusOut>', lambda _: update_config())
        steam_entry.bind('<FocusOut>', lambda _: update_config())
        studiomdl_entry.bind('<FocusOut>', lambda _: update_config())
        vtfcmd_entry.bind('<FocusOut>', lambda _: update_config())
        namespace_entry.bind('<FocusOut>', lambda _: update_config())

        # Close button
        self._button(popup, "Done", popup.destroy,
                     bg=self.ACCENT, fg='#ffffff').pack(pady=(0, 10))

    def browse_input(self):
        t = self.input_type.get()
        if t == 'File':
            path = filedialog.askopenfilename(
                title="Select addon or model file",
                filetypes=[
                    ("Supported files", "*.gma *.bin *.vpk *.mdl"),
                    ("Garry's Mod Addon", "*.gma *.bin"),
                    ("Valve Pak", "*.vpk"),
                    ("Source Model", "*.mdl"),
                ])
        elif t == 'Folder':
            path = filedialog.askdirectory(title="Select folder with models or addon files")
        else:
            path = ''
        if path:
            self.input_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.output_dir.set(path)

    def abort_process(self):
        self.abort_flag['abort'] = True
        self.log_widget.insert('end', '[INFO] Abort requested. Waiting for current operation to finish...\n')
        self.log_widget.see('end')

    def copy_console_output(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_widget.get('1.0', tk.END))
        self.root.update()
        messagebox.showinfo("Copied!", "Console output copied to clipboard.")

    def _update_health_bar(self):
        def dot_color(path, check_fn):
            return self.GREEN if path and check_fn(path) else self.RED
        self._dot_steamcmd.config(fg=dot_color(self.steamcmd_path.get(), os.path.isfile))
        self._dot_crowbar.config(fg=dot_color(self.crowbarcli_path.get(), os.path.isfile))
        self._dot_output.config(fg=dot_color(self.output_dir.get(), os.path.isdir))
        self._dot_studiomdl.config(fg=dot_color(self.studiomdl_path.get(), os.path.isfile))
        self._dot_vtfcmd.config(fg=dot_color(self.vtfcmd_path.get(), os.path.isfile))

    def _show_instructions(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Instructions")
        dlg.geometry("620x500")
        dlg.configure(bg=self.BG)
        dlg.transient(self.root)
        instructions_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'info', 'instructions.txt')
        text = scrolledtext.ScrolledText(
            dlg, bg=self.SURFACE, fg=self.FG, font=self.FONT,
            relief='solid', bd=1, wrap='word')
        text.pack(fill='both', expand=True, padx=14, pady=(14, 4))
        try:
            with open(instructions_path, 'r', encoding='utf-8') as f:
                text.insert('1.0', f.read())
        except Exception:
            text.insert('1.0', 'Instructions file not found.')
        text.config(state='disabled')
        self._button(dlg, 'Close', dlg.destroy).pack(pady=(0, 10))

    # ── TYPE options shared by batch dialog ─────────────────────────
    _TYPE_OPTIONS = [
        ('Victim Model',          'victim_playermodel'),
        ('Bear Model',            'bear_playermodel'),
        ('Accessory',             'accessory'),
        ('SWEP',                  'swep'),
        ('VIP Victim Model',      'victim_vip'),
        ('VIP Bear Model',        'bear_vip'),
        ('Reserved Victim Model', 'victim_reserved'),
        ('Reserved Bear Model',   'bear_reserved'),
    ]

    def show_batch_config_dialog(self, model_data_list):
        """
        Show a single dialog to configure all models at once.
        model_data_list: list of dicts with keys:
            mdl_path, model_name, bodygroups, skin_count, arms_path
        Returns list of config dicts for non-skipped models, or None on cancel.
        """
        type_labels  = [t[0] for t in self._TYPE_OPTIONS]
        type_key     = {t[0]: t[1] for t in self._TYPE_OPTIONS}

        dlg = tk.Toplevel(self.root)
        dlg.title(f'Batch Configure — {len(model_data_list)} model(s)')
        dlg.geometry('900x560')
        dlg.configure(bg=self.BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.focus_force()
        dlg.resizable(True, True)

        result = {'configs': None}

        # ── Bulk apply header ─────────────────────────────────────────
        hdr = self._frame(dlg)
        hdr.pack(fill='x', padx=14, pady=(10, 4))
        self._label(hdr, 'Set all:', font=self.FONT_BOLD).pack(side='left')
        bulk_type_var = tk.StringVar(value='Victim Model')
        ttk.Combobox(hdr, textvariable=bulk_type_var, values=type_labels,
                     state='readonly', width=22, font=self.FONT).pack(side='left', padx=(6, 8))
        self._label(hdr, 'Price:').pack(side='left')
        bulk_price_var = tk.StringVar(value='1000')
        self._entry(hdr, bulk_price_var, width=8).pack(side='left', padx=(4, 8))

        # ── Column header row ─────────────────────────────────────────
        col_hdr = self._frame(dlg)
        col_hdr.pack(fill='x', padx=14, pady=(4, 0))
        for text, w in [('', 2), ('Item Name', 22), ('Type', 22), ('Price', 8), ('Info', 16), ('Path', 0)]:
            self._label(col_hdr, text, width=w, font=self.FONT_BOLD, anchor='w').pack(side='left', padx=(0, 4))
        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(2, 0))

        # ── Scrollable row list ───────────────────────────────────────
        container = self._frame(dlg)
        container.pack(fill='both', expand=True, padx=14, pady=4)
        canvas = tk.Canvas(container, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        scrollable = self._frame(canvas)
        scrollable.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scrollable, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mw(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mw)
        dlg.bind('<Destroy>', lambda _: canvas.unbind_all('<MouseWheel>'))
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        def _show_adv_popup(row):
            pop = tk.Toplevel(dlg)
            pop.title(f"Advanced — {row['data']['model_name']}")
            pop.configure(bg=self.BG)
            pop.transient(dlg)
            pop.resizable(False, False)
            adv = row['adv']

            def _row(label, widget_fn, hint=''):
                f = self._frame(pop)
                f.pack(fill='x', padx=14, pady=4)
                self._label(f, label, width=14, anchor='w').pack(side='left')
                widget_fn(f)
                if hint:
                    self._label(f, hint, fg='#999999', font=('Segoe UI', 9)).pack(side='left', padx=(6, 0))

            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(10, 2))
            self._label(pop, 'Flags', font=self.FONT_BOLD).pack(anchor='w', padx=14, pady=(6, 0))
            for var, label, hint in [
                (adv['hidden'], 'Hidden', 'visible only to owners & superadmins'),
            ]:
                f = self._frame(pop)
                f.pack(fill='x', padx=14, pady=2)
                ttk.Checkbutton(f, variable=var).pack(side='left')
                self._label(f, label, width=14).pack(side='left')
                self._label(f, hint, fg='#999999', font=('Segoe UI', 9)).pack(side='left', padx=(4, 0))

            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))
            self._label(pop, 'Type-specific', font=self.FONT_BOLD).pack(anchor='w', padx=14, pady=(6, 0))
            _row('Class Name', lambda f: self._entry(f, adv['class_name'], width=24).pack(side='left'), '(SWEP only)')
            _row('Reserved for', lambda f: self._entry(f, adv['reserved_for'], width=24).pack(side='left'), '(reserved types — comma-sep for multiple)')

            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))
            self._button(pop, 'Close', pop.destroy).pack(pady=(4, 10))
            pop.update_idletasks()
            pop.geometry(f'480x{pop.winfo_reqheight()}')

        # Group models by suggested_type in _TYPE_OPTIONS display order
        _type_order     = [t[1] for t in self._TYPE_OPTIONS]
        _type_label_map = {t[1]: t[0] for t in self._TYPE_OPTIONS}
        _groups = defaultdict(list)
        for data in model_data_list:
            _groups[data.get('suggested_type', 'victim_playermodel')].append(data)
        _ordered = []
        for _tk in _type_order:
            if _groups[_tk]:
                _ordered.append(('_header', _tk))
                _ordered.extend(_groups[_tk])
        for _tk, _items in _groups.items():
            if _tk not in _type_order:
                _ordered.extend(_items)

        rows = []
        for _item in _ordered:
            if isinstance(_item, tuple) and _item[0] == '_header':
                _htype = _item[1]
                _count = len(_groups[_htype])
                hf = self._frame(scrollable)
                hf.pack(fill='x', pady=(8, 2))
                ttk.Separator(hf, orient='horizontal').pack(
                    fill='x', side='left', expand=True, padx=(0, 8))
                self._label(hf, f'{_type_label_map[_htype]}  ({_count})',
                            font=self.FONT_BOLD, fg=self.ACCENT).pack(side='left')
                ttk.Separator(hf, orient='horizontal').pack(
                    fill='x', side='left', expand=True, padx=(8, 0))
                continue
            data = _item
            rf = self._frame(scrollable)
            rf.pack(fill='x', pady=1)

            include_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(rf, variable=include_var).pack(side='left', padx=(0, 4))

            stem = os.path.splitext(data['model_name'])[0]
            name_var = tk.StringVar(value=stem)
            self._entry(rf, name_var, width=22).pack(side='left', padx=(0, 4))

            _type_key_to_label = {k: lbl for lbl, k in self._TYPE_OPTIONS}
            _suggested_label = _type_key_to_label.get(
                data.get('suggested_type', 'victim_playermodel'), 'Victim Model'
            )
            type_var = tk.StringVar(value=_suggested_label)
            ttk.Combobox(rf, textvariable=type_var, values=type_labels,
                         state='readonly', width=20, font=self.FONT).pack(side='left', padx=(0, 4))

            price_var = tk.StringVar(value='1000')
            self._entry(rf, price_var, width=8).pack(side='left', padx=(0, 4))

            info_parts = []
            if data['bodygroups']:
                info_parts.append(f"{len(data['bodygroups'])} BG")
            if data['skin_count']:
                info_parts.append(f"{data['skin_count']} skins")
            if data['arms_path']:
                info_parts.append('arms ✓')
            self._label(rf, ', '.join(info_parts) if info_parts else '—',
                        fg='#666666', width=14).pack(side='left')

            adv = {
                'color2_proxy': tk.BooleanVar(value=False),
                'hidden':       tk.BooleanVar(value=False),
                'class_name':   tk.StringVar(value=f'weapon_{stem.lower()}'),
                'reserved_for': tk.StringVar(value=''),
            }
            row = {'data': data, 'include_var': include_var,
                   'name_var': name_var, 'type_var': type_var,
                   'price_var': price_var, 'adv': adv,
                   'frame': rf, 'selected': False}
            rf.bind('<Button-3>', lambda e, r=row: _toggle_row_selection(r))

            _c2_btn = tk.Button(rf, text='C2', font=self.FONT,
                                bg=self.BG, fg='#555555',
                                relief='flat', bd=1, padx=4, pady=1,
                                cursor='hand2')
            def _make_c2_toggle(btn, var):
                def _toggle():
                    var.set(not var.get())
                    if var.get():
                        btn.config(bg='#4a9eff', fg='#ffffff', relief='sunken')
                    else:
                        btn.config(bg=self.BG, fg='#555555', relief='flat')
                return _toggle
            _c2_btn.config(command=_make_c2_toggle(_c2_btn, adv['color2_proxy']))
            _c2_btn.pack(side='left', padx=(4, 0))

            self._button(rf, 'Adv.', lambda r=row: _show_adv_popup(r),
                         bg=self.BG, fg=self.FG).pack(side='left', padx=(4, 0))

            self._label(rf, data['mdl_path'].replace('\\', '/'),
                        fg='#555555', font=('Segoe UI', 8),
                        anchor='w').pack(side='left', padx=(12, 4))

            rows.append(row)

        _SELECTED_BG   = '#2a4a6a'
        _UNSELECTED_BG = self.BG

        def _toggle_row_selection(row, event=None):
            row['selected'] = not row['selected']
            bg = _SELECTED_BG if row['selected'] else _UNSELECTED_BG
            row['frame'].config(bg=bg)
            for child in row['frame'].winfo_children():
                try:
                    child.config(bg=bg)
                except tk.TclError:
                    pass

        def apply_to_all():
            t, p = bulk_type_var.get(), bulk_price_var.get()
            for row in rows:
                if row['include_var'].get():
                    row['type_var'].set(t)
                    row['price_var'].set(p)

        def _force_type_all(*_):
            t = bulk_type_var.get()
            for row in rows:
                if row['include_var'].get():
                    row['type_var'].set(t)
        bulk_type_var.trace_add('write', _force_type_all)

        def _apply_to_selected():
            t, p = bulk_type_var.get(), bulk_price_var.get()
            for row in rows:
                if row['selected']:
                    row['type_var'].set(t)
                    row['price_var'].set(p)

        def _clear_selection():
            for row in rows:
                row['selected'] = False
                row['frame'].config(bg=_UNSELECTED_BG)
                for child in row['frame'].winfo_children():
                    try:
                        child.config(bg=_UNSELECTED_BG)
                    except tk.TclError:
                        pass

        _AUTO_TYPES = [
            ('Victim Model',  'victim_playermodel'),
            ('Bear Model',    'bear_playermodel'),
            ('Accessory',     'accessory'),
            ('SWEP',          'swep'),
        ]
        _auto_type_labels = [t[0] for t in _AUTO_TYPES]
        _auto_type_key    = {t[0]: t[1] for t in _AUTO_TYPES}
        _auto_label_key   = {t[1]: t[0] for t in _AUTO_TYPES}

        def _show_keyword_editor():
            pop = tk.Toplevel(dlg)
            pop.title('Type Keyword Rules')
            pop.configure(bg=self.BG)
            pop.transient(dlg)
            pop.resizable(False, False)

            self._label(pop, 'Keywords matched against model path/filename (case-insensitive)',
                        fg='#999999', font=('Segoe UI', 9)).pack(anchor='w', padx=14, pady=(10, 2))

            list_frame = self._frame(pop)
            list_frame.pack(fill='both', expand=True, padx=14, pady=4)

            # header
            hf = self._frame(list_frame)
            hf.pack(fill='x')
            self._label(hf, 'Keyword', width=20, font=self.FONT_BOLD, anchor='w').pack(side='left')
            self._label(hf, 'Type', width=18, font=self.FONT_BOLD, anchor='w').pack(side='left')
            ttk.Separator(list_frame, orient='horizontal').pack(fill='x', pady=(2, 4))

            # scrollable keyword rows
            kw_canvas   = tk.Canvas(list_frame, bg=self.BG, highlightthickness=0, height=180)
            kw_scroll   = ttk.Scrollbar(list_frame, orient='vertical', command=kw_canvas.yview)
            kw_scrollable = self._frame(kw_canvas)
            kw_scrollable.bind('<Configure>', lambda e: kw_canvas.configure(
                scrollregion=kw_canvas.bbox('all')))
            kw_canvas.create_window((0, 0), window=kw_scrollable, anchor='nw')
            kw_canvas.configure(yscrollcommand=kw_scroll.set)
            kw_canvas.pack(side='left', fill='both', expand=True)
            kw_scroll.pack(side='right', fill='y')

            kw_rows = []  # list of (kw_var, type_var, frame)

            def _refresh_rows():
                for w in kw_scrollable.winfo_children():
                    w.destroy()
                kw_rows.clear()
                for kw, tkey in list(self.custom_type_keywords.items()):
                    rf2 = self._frame(kw_scrollable)
                    rf2.pack(fill='x', pady=1)
                    kw_var  = tk.StringVar(value=kw)
                    type_var2 = tk.StringVar(value=_auto_label_key.get(tkey, 'Victim Model'))
                    self._entry(rf2, kw_var, width=20).pack(side='left', padx=(0, 6))
                    cb = ttk.Combobox(rf2, textvariable=type_var2,
                                      values=_auto_type_labels,
                                      state='readonly', width=16, font=self.FONT)
                    cb.pack(side='left')
                    kw_rows.append((kw_var, type_var2, rf2))

            _refresh_rows()

            # Add row
            add_frame = self._frame(pop)
            add_frame.pack(fill='x', padx=14, pady=(6, 2))
            new_kw_var = tk.StringVar()
            self._label(add_frame, 'New keyword:', anchor='w').pack(side='left')
            self._entry(add_frame, new_kw_var, width=16).pack(side='left', padx=(6, 6))

            def _add_keyword():
                kw = new_kw_var.get().strip().lower()
                if not kw:
                    return
                self.custom_type_keywords[kw] = 'victim_playermodel'
                new_kw_var.set('')
                _refresh_rows()

            self._button(add_frame, '+ Add', _add_keyword,
                         bg=self.ACCENT, fg='#ffffff').pack(side='left')

            def _remove_last_selected():
                if kw_rows:
                    kw_var, _, rf2 = kw_rows[-1]
                    kw = kw_var.get().strip().lower()
                    self.custom_type_keywords.pop(kw, None)
                    rf2.destroy()
                    kw_rows.pop()

            self._button(add_frame, '− Remove last', _remove_last_selected,
                         bg=self.BG, fg=self.FG).pack(side='left', padx=(6, 0))

            def _save_and_reapply():
                # Persist current entries to custom_type_keywords
                new_kws = {}
                for kw_var, type_var2, _ in kw_rows:
                    kw = kw_var.get().strip().lower()
                    if kw:
                        new_kws[kw] = _auto_type_key.get(type_var2.get(), 'victim_playermodel')
                self.custom_type_keywords = new_kws
                save_custom_keywords(new_kws)
                # Re-suggest all rows
                _type_key_to_label = {k: lbl for lbl, k in self._TYPE_OPTIONS}
                for row in rows:
                    suggested = self._suggest_item_type(
                        row['data']['mdl_path'], row['data']['arms_path'])
                    label = _type_key_to_label.get(suggested, 'Victim Model')
                    row['type_var'].set(label)

            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))
            btn_f = self._frame(pop)
            btn_f.pack(padx=14, pady=(4, 10))
            self._button(btn_f, 'Re-suggest all rows', _save_and_reapply,
                         bg=self.ACCENT, fg='#ffffff').pack(side='left', padx=(0, 8))

            def _on_close():
                _save_and_reapply()
                pop.destroy()

            self._button(btn_f, 'Close', _on_close).pack(side='left')
            pop.update_idletasks()
            pop.geometry(f'400x{min(pop.winfo_reqheight(), 520)}')

        self._button(hdr, 'Apply to All', apply_to_all,
                     bg=self.ACCENT, fg='#ffffff').pack(side='left')
        self._button(hdr, 'Apply to selected', _apply_to_selected,
                     bg=self.BG, fg=self.FG).pack(side='left', padx=(6, 0))
        self._button(hdr, 'Clear sel.', _clear_selection,
                     bg=self.BG, fg=self.FG).pack(side='left', padx=(4, 0))
        self._button(hdr, 'Keyword Rules…', _show_keyword_editor,
                     bg=self.BG, fg=self.FG).pack(side='left', padx=(12, 0))

        # ── Buttons ───────────────────────────────────────────────────
        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(4, 0))
        btn_bar = self._frame(dlg)
        btn_bar.pack(fill='x', padx=14, pady=(4, 10))

        def on_cancel():
            result['configs'] = None
            dlg.destroy()

        def on_generate():
            configs = []
            for row in rows:
                if not row['include_var'].get():
                    continue
                name = row['name_var'].get().strip()
                if not name:
                    messagebox.showwarning('Invalid Name',
                        f'Model "{row["data"]["model_name"]}" has no name set.', parent=dlg)
                    return
                try:
                    price = int(row['price_var'].get().strip())
                    if price < 0:
                        raise ValueError()
                except ValueError:
                    messagebox.showwarning('Invalid Price',
                        f'"{name}" has an invalid price — enter 0 or a positive integer.', parent=dlg)
                    return
                item_type = type_key.get(row['type_var'].get(), 'victim_playermodel')
                adv = row['adv']
                raw_reserved = adv['reserved_for'].get().strip()
                configs.append({
                    'mdl_path':        row['data']['mdl_path'],
                    'name':            name,
                    'price':           price,
                    'type':            item_type,
                    'arms_path':       row['data']['arms_path'],
                    'use_color2_proxy': adv['color2_proxy'].get(),
                    'hidden':          adv['hidden'].get(),
                    'class_name':      adv['class_name'].get().strip() or 'weapon_unknown',
                    'reserved_for':    raw_reserved or None,
                    'bodygroups':      row['data']['bodygroups'],
                    'skin_count':      row['data']['skin_count'],
                })

            if not configs:
                messagebox.showwarning('Nothing to Generate',
                    'No models are checked for generation.', parent=dlg)
                return

            result['configs'] = configs
            dlg.destroy()

        self._button(btn_bar, 'Cancel', on_cancel,
                     bg=self.RED, fg='#ffffff').pack(side='left')
        included = len(model_data_list)
        self._button(btn_bar, f'Generate ({included} model(s))', on_generate,
                     bg=self.GREEN, fg='#ffffff').pack(side='right')

        self.root.wait_window(dlg)
        return result['configs']

    def _collect_reserved_steamids(self, reserved_configs, parent=None):
        """Prompt for Steam IDs for reserved-type configs. Modifies configs in-place."""
        dlg = tk.Toplevel(parent or self.root)
        dlg.title('Reserved Models — Steam IDs')
        dlg.geometry('580x40')
        dlg.configure(bg=self.BG)
        dlg.transient(parent or self.root)
        dlg.grab_set()

        self._label(dlg,
            'Enter Steam ID(s) for each reserved model (comma-separated for multiple):',
            font=self.FONT).pack(padx=14, pady=(10, 6), anchor='w')

        steamid_vars = []
        for cfg in reserved_configs:
            f = self._frame(dlg)
            f.pack(fill='x', padx=14, pady=3)
            self._label(f, cfg['name'], width=26, anchor='w').pack(side='left')
            var = tk.StringVar(value='STEAM_0:0:12345678')
            self._entry(f, var).pack(side='left', fill='x', expand=True, padx=(6, 0))
            steamid_vars.append((cfg, var))

        # resize to fit content
        dlg.update_idletasks()
        h = max(200, 80 + len(reserved_configs) * 36)
        dlg.geometry(f'580x{h}')

        result = {'ok': False}

        def on_ok():
            for cfg, var in steamid_vars:
                raw = var.get().strip()
                if ',' in raw:
                    cfg['reserved_for'] = [s.strip() for s in raw.split(',') if s.strip()]
                else:
                    cfg['reserved_for'] = raw
            result['ok'] = True
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btn_bar = self._frame(dlg)
        btn_bar.pack(fill='x', padx=14, pady=(8, 10))
        self._button(btn_bar, 'Cancel', on_cancel).pack(side='left')
        self._button(btn_bar, 'OK', on_ok,
                     bg=self.GREEN, fg='#ffffff').pack(side='right')

        self.root.wait_window(dlg)
        return result['ok']

    def _collect_swep_classnames(self, swep_configs, parent=None):
        """Prompt for SWEP ClassName for each swep-type config. Modifies configs in-place."""
        dlg = tk.Toplevel(parent or self.root)
        dlg.title('SWEP Items — Class Names')
        dlg.configure(bg=self.BG)
        dlg.transient(parent or self.root)
        dlg.grab_set()

        self._label(dlg,
            'Enter the SWEP class name for each weapon item (e.g. weapon_vape):',
            font=self.FONT).pack(padx=14, pady=(10, 6), anchor='w')

        classname_vars = []
        for cfg in swep_configs:
            f = self._frame(dlg)
            f.pack(fill='x', padx=14, pady=3)
            self._label(f, cfg['name'], width=26, anchor='w').pack(side='left')
            stem = os.path.splitext(os.path.basename(cfg['mdl_path']))[0].lower()
            var = tk.StringVar(value=f'weapon_{stem}')
            self._entry(f, var).pack(side='left', fill='x', expand=True, padx=(6, 0))
            classname_vars.append((cfg, var))

        dlg.update_idletasks()
        h = max(180, 80 + len(swep_configs) * 36)
        dlg.geometry(f'580x{h}')

        result = {'ok': False}

        def on_ok():
            for cfg, var in classname_vars:
                cfg['class_name'] = var.get().strip() or 'weapon_unknown'
            result['ok'] = True
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btn_bar = self._frame(dlg)
        btn_bar.pack(fill='x', padx=14, pady=(8, 10))
        self._button(btn_bar, 'Cancel', on_cancel).pack(side='left')
        self._button(btn_bar, 'OK', on_ok,
                     bg=self.GREEN, fg='#ffffff').pack(side='right')

        self.root.wait_window(dlg)
        return result['ok']

    def start_process(self):
        self.process_button.config(state='disabled')
        threading.Thread(target=self.process_workflow, daemon=True).start()

    def process_workflow(self):
        self.log_widget.insert('end', '[INFO] Processing started...\n')
        self.log_widget.see('end')
        input_type = self.input_type.get()
        input_path = self.input_path.get()
        output_dir = self.output_dir.get()
        steamcmd_path = self.steamcmd_path.get()
        crowbarcli_path = self.crowbarcli_path.get()
        write_bodygroups = self.write_bodygroups.get()
        download_only = self.download_only.get()
        game_name = self.game_choice.get()
        app_id = self.GAMES.get(game_name, '4000')

        if app_id != '4000':
            self._append_log(f'[INFO] Game: {game_name} (App ID: {app_id})')
        try:
            if input_type == 'File':
                if input_path.lower().endswith('.mdl'):
                    # Single .mdl file — skip extraction, process directly
                    self._append_log(f'[INFO] Direct .mdl input: {input_path}')
                    if not self._process_mdl_list(
                            [input_path], output_dir, crowbarcli_path,
                            write_bodygroups, self._append_log):
                        self.process_button.config(state='normal')
                        return
                elif input_path.lower().endswith('.bsp'):
                    # Skip BSP (map) files
                    self._append_log(f'[INFO] Skipped .bsp file (map file, contains no models): {os.path.basename(input_path)}')
                else:
                    # Single .gma, .bin, or .vpk file
                    extract_dir = os.path.join(output_dir, 'extracted')
                    os.makedirs(extract_dir, exist_ok=True)
                    extract_archive(input_path, extract_dir, self._append_log)
                    gma_name = os.path.splitext(os.path.basename(input_path))[0]
                    gma_folder = os.path.join(extract_dir, gma_name)
                    if not os.path.isdir(gma_folder):
                        self._append_log(f'[WARN] Expected folder {gma_folder} not found after extraction.')
                        return
                    mdl_files = self.find_mdl_files(gma_folder)
                    if not mdl_files:
                        self._append_log(f'[INFO] Skipped addon "{gma_name}" — no .mdl files found.')
                    else:
                        if not self._process_mdl_list(mdl_files, output_dir, crowbarcli_path,
                                                      write_bodygroups, self._append_log):
                            self.process_button.config(state='normal')
                            return
            elif input_type == 'Folder':
                # Folder may contain addon files (needs extraction) and/or
                # already-extracted model content (.mdl files directly).
                archive_files = []
                loose_mdl_files = []
                skipped_bsp_count = 0
                for root, dirs, files in os.walk(input_path):
                    for f in files:
                        fl = f.lower()
                        if fl.endswith('.bsp'):
                            # Skip BSP (map) files
                            skipped_bsp_count += 1
                        elif fl.endswith(('.gma', '.bin', '.vpk')):
                            archive_files.append(os.path.join(root, f))
                        elif fl.endswith('.mdl'):
                            loose_mdl_files.append(os.path.join(root, f))

                if skipped_bsp_count > 0:
                    self._append_log(f'[INFO] Skipped {skipped_bsp_count} .bsp file(s) (map files, contain no models)')

                all_mdl_files = list(loose_mdl_files)
                skipped_addon_count = 0

                if archive_files:
                    self._append_log(f'[INFO] Found {len(archive_files)} addon file(s) — extracting...')
                    for archive_path in archive_files:
                        archive_file = os.path.basename(archive_path)
                        addon_name = os.path.splitext(archive_file)[0]
                        extract_dir = os.path.join(output_dir, 'extracted', addon_name)
                        os.makedirs(extract_dir, exist_ok=True)
                        extract_archive(archive_path, extract_dir, self._append_log)
                        extracted_mdls = self.find_mdl_files(extract_dir)
                        if not extracted_mdls:
                            self._append_log(f'[INFO] Skipped addon "{addon_name}" — no .mdl files found.')
                            skipped_addon_count += 1
                        else:
                            all_mdl_files.extend(extracted_mdls)

                if loose_mdl_files:
                    self._append_log(f'[INFO] Found {len(loose_mdl_files)} loose .mdl file(s) in folder.')

                if skipped_addon_count > 0:
                    self._append_log(f'[INFO] Skipped {skipped_addon_count} addon(s) with no models.')

                if not all_mdl_files:
                    self._append_log('[WARN] No .mdl files found in folder after processing.')
                else:
                    if not self._process_mdl_list(all_mdl_files, output_dir, crowbarcli_path,
                                                  write_bodygroups, self._append_log):
                        self.process_button.config(state='normal')
                        return
            elif input_type == 'Workshop' or input_type == 'Collection':
                use_steamcmd = (app_id == '4000')

                if use_steamcmd:
                    # Clean the SteamCMD steamapps workshop content folder to avoid contamination
                    steamcmd_dir = os.path.dirname(os.path.normpath(steamcmd_path))
                    steamapps_content_dir = os.path.normpath(os.path.join(steamcmd_dir, 'steamapps', 'workshop', 'content', app_id))
                    try:
                        if os.path.isdir(steamapps_content_dir):
                            import shutil
                            shutil.rmtree(steamapps_content_dir)
                            self._append_log(f'[INFO] Deleted old workshop content folder: {steamapps_content_dir}')
                    except Exception as e:
                        self._append_log(f'[WARN] Could not delete workshop content folder: {e}')

                if input_type == 'Workshop':
                    workshop_id = input_path.strip()
                    # Extract numeric ID from URL if needed
                    id_match = re.search(r'id=(\d+)', workshop_id)
                    if id_match:
                        workshop_id = id_match.group(1)

                    if use_steamcmd:
                        gma_file = download_workshop_item(steamcmd_path, workshop_id, output_dir, log_callback, app_id=app_id)
                    else:
                        self._append_log(f'[INFO] Looking for workshop item {workshop_id} in Steam library...')
                        gma_file = find_workshop_in_steam(self.steam_path.get(), app_id, workshop_id, output_dir, self._append_log)

                    if self.download_only.get():
                        if gma_file:
                            self._append_log('[INFO] Workshop download complete (download only mode).')
                        else:
                            self._append_log('[ERROR] Failed to download workshop item.' if use_steamcmd
                                         else '[ERROR] Workshop item not found in Steam library. Subscribe to it in Steam first.')
                        return
                    if gma_file:
                        addon_name = os.path.splitext(os.path.basename(gma_file))[0]
                        extract_dir = os.path.join(output_dir, 'extracted', addon_name)
                        os.makedirs(extract_dir, exist_ok=True)
                        extract_archive(gma_file, extract_dir, self._append_log)
                        mdl_files = self.find_mdl_files(extract_dir)
                        
                        if not mdl_files:
                            self._append_log(f'[INFO] Skipped workshop item "{addon_name}" — no .mdl files found.')
                        else:
                            if not self._process_mdl_list(mdl_files, output_dir, crowbarcli_path,
                                                          write_bodygroups, self._append_log):
                                self.process_button.config(state='normal')
                                return
                    else:
                        if use_steamcmd:
                            self._append_log('[ERROR] Failed to download or extract workshop item.')
                        else:
                            self._append_log('[ERROR] Workshop item not found in Steam library. Subscribe to it in Steam and make sure the game has downloaded it.')

                elif input_type == 'Collection':
                    # Parse collection items from the web page
                    from steamcmd_downloader import parse_collection_items
                    item_ids = parse_collection_items(input_path.strip(), self._append_log)
                    if not item_ids:
                        self._append_log('[ERROR] No items found in collection.')
                        return

                    if use_steamcmd:
                        gma_files = download_collection(steamcmd_path, input_path, output_dir, log_callback, app_id=app_id)
                    else:
                        self._append_log(f'[INFO] Looking for {len(item_ids)} collection item(s) in Steam library...')
                        gma_files = []
                        for idx, item_id in enumerate(item_ids, 1):
                            self._append_log(f'[INFO] Searching for item {idx}/{len(item_ids)}: {item_id}')
                            result = find_workshop_in_steam(self.steam_path.get(), app_id, item_id, output_dir, self._append_log)
                            if result:
                                gma_files.append(result)
                            else:
                                self._append_log(f'[WARN] Item {item_id} not found in Steam library — skipping.')

                    if self.download_only.get():
                        if gma_files:
                            self._append_log(f'[INFO] Collection complete — found {len(gma_files)} item(s) (download only mode).')
                        else:
                            self._append_log('[ERROR] Failed to find any items from collection.')
                        return
                    if gma_files:
                        self._append_log(f'[INFO] All collection items located. Beginning extraction and processing...')
                        
                        # Collect all mdl files first
                        all_mdl_files = []
                        skipped_addon_count = 0
                        for gma_file in gma_files:
                            addon_name = os.path.splitext(os.path.basename(gma_file))[0]
                            extract_dir = os.path.join(output_dir, 'extracted', addon_name)
                            os.makedirs(extract_dir, exist_ok=True)
                            extract_archive(gma_file, extract_dir, self._append_log)
                            mdl_files = self.find_mdl_files(extract_dir)
                            if not mdl_files:
                                self._append_log(f'[INFO] Skipped collection item "{addon_name}" — no .mdl files found.')
                                skipped_addon_count += 1
                            else:
                                all_mdl_files.extend(mdl_files)
                        
                        if skipped_addon_count > 0:
                            self._append_log(f'[INFO] Skipped {skipped_addon_count} collection item(s) with no models.')
                        
                        # Process all models from collection
                        if all_mdl_files:
                            if not self._process_mdl_list(all_mdl_files, output_dir, crowbarcli_path,
                                                          write_bodygroups, self._append_log):
                                self.process_button.config(state='normal')
                                return
                    else:
                        self._append_log('[ERROR] Failed to download or extract any items from collection.')
        except Exception as e:
            self.log_widget.insert('end', f'[ERROR] {e}\n')
            self.log_widget.see('end')
        self.process_button.config(state='normal')

    def find_mdl_files(self, folder):
        mdl_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.endswith('.mdl'):
                    mdl_files.append(os.path.join(root, file))
        return mdl_files

    def find_qc_file(self, folder):
        for fname in os.listdir(folder):
            if fname.endswith('.qc'):
                return os.path.join(folder, fname)
        return None

    def _process_mdl_list(self, mdl_files, output_dir, crowbarcli_path,
                          write_bodygroups, log_callback):
        """
        Two-phase pipeline: decompile all → batch config dialog → write Lua.
        Returns False if the user cancelled, True otherwise.
        """
        if not mdl_files:
            log_callback('[WARN] No .mdl files found.')
            return True

        # NPC filter
        mdl_files = filter_npc_paths(mdl_files)

        # Deduplication
        original_count = len(mdl_files)
        unique_mdls = {}
        for p in mdl_files:
            normalized = os.path.normpath(p).lower()
            if normalized not in unique_mdls:
                unique_mdls[normalized] = p
        mdl_files = list(unique_mdls.values())
        if original_count > len(mdl_files):
            log_callback(f'[INFO] Removed {original_count - len(mdl_files)} duplicate model(s) from list')

        if not mdl_files:
            log_callback('[WARN] No models remain after filtering.')
            return True

        # ── Phase A: decompile all, build records keyed by $modelname ────────
        log_callback(f'[INFO] Phase A — Decompiling {len(mdl_files)} model(s)...')
        records = []
        for idx, mdl_path in enumerate(mdl_files):
            model_name     = os.path.basename(mdl_path)
            crowbar_outdir = os.path.join(
                output_dir, 'crowbar_out', f'{idx:04d}_{os.path.splitext(model_name)[0]}'
            )
            decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback, quiet=True)
            qc_path = self.find_qc_file(crowbar_outdir)
            if qc_path:
                signals   = parse_qc_type_signals(qc_path)
                modelname = (parse_qc_modelname(qc_path) or '').replace('\\', '/').lower()
                is_arms   = signals['has_c_arms_include']
            else:
                log_callback(f'[WARN] No QC file found for {model_name}')
                signals   = None
                modelname = ''
                is_arms   = False
            records.append({
                'mdl_path':       mdl_path,
                'crowbar_outdir': crowbar_outdir,
                'qc_path':        qc_path,
                'modelname':      modelname,
                'is_arms':        is_arms,
                'signals':        signals,
            })

        arms_records = [r for r in records if r['is_arms']]
        main_records = [r for r in records if not r['is_arms']]

        for r in arms_records:
            log_callback(f'[INFO] Arms (QC): {os.path.basename(r["mdl_path"])}  [{r["modelname"]}]')

        if not main_records:
            log_callback('[WARN] All models classified as arms; nothing to generate.')
            return True

        # Pair arms to main models via $modelname game directory + stem matching
        def _strip_arms_stem(stem):
            s = stem.lower()
            for prefix in ('c_arms_', 'c_hands_'):
                if s.startswith(prefix):
                    return s[len(prefix):]
            if '_arms_' in s:
                return s.replace('_arms_', '_')
            for suffix in ('_arms', 'arms'):
                if s.endswith(suffix) and len(s) > len(suffix):
                    return s[:-len(suffix)]
            return s

        def _stems_match(ar_stripped, mr_stem):
            if not ar_stripped:
                return False
            if (ar_stripped == mr_stem or
                    ar_stripped in mr_stem or
                    mr_stem.startswith(ar_stripped)):
                return True
            # Token-subset: all underscore-split tokens of arms stem present in player stem
            ar_tokens = set(ar_stripped.split('_'))
            mr_tokens = set(mr_stem.split('_'))
            return len(ar_tokens) > 1 and ar_tokens <= mr_tokens

        arms_by_gamedir = defaultdict(list)
        for r in arms_records:
            mn = r['modelname']
            d  = mn.rsplit('/', 1)[0] if '/' in mn else ''
            arms_by_gamedir[d].append(r)
            parent = d.rsplit('/', 1)[0] if '/' in d else ''
            if parent and parent != d:
                arms_by_gamedir[parent].append(r)

        for r in main_records:
            mn      = r['modelname']
            d       = mn.rsplit('/', 1)[0] if '/' in mn else ''
            mr_stem = os.path.splitext(os.path.basename(r['mdl_path']))[0].lower()
            cands   = arms_by_gamedir.get(d, [])
            best    = None
            for ar in cands:
                ar_stripped = _strip_arms_stem(
                    os.path.splitext(os.path.basename(ar['mdl_path']))[0].lower()
                )
                if _stems_match(ar_stripped, mr_stem):
                    best = ar
                    break
            r['arms_record'] = best
            if best:
                log_callback(
                    f'[INFO] Arms paired: {os.path.basename(best["mdl_path"])} '
                    f'→ {os.path.basename(r["mdl_path"])}'
                )

        # ── Phase B: build model_data_list from main records ─────────────
        log_callback(f'[INFO] Phase B — Building config for {len(main_records)} model(s)...')
        model_data_list = []
        for r in main_records:
            mdl_path   = r['mdl_path']
            model_name = os.path.basename(mdl_path)
            qc_path    = r['qc_path']
            signals    = r['signals']
            qc_hint    = infer_type_from_qc(signals) if signals else None

            bodygroups = parse_qc_bodygroups(qc_path) if (qc_path and write_bodygroups) else []
            skin_count = parse_qc_skins(qc_path)      if (qc_path and write_bodygroups) else 0

            arms_r = r.get('arms_record')
            if arms_r and arms_r['modelname']:
                mn       = arms_r['modelname']
                arms_rel = mn[mn.find('models/'):] if 'models/' in mn else mn
            else:
                arms_rel = None

            model_data_list.append({
                'mdl_path':       mdl_path,
                'model_name':     model_name,
                'bodygroups':     bodygroups,
                'skin_count':     skin_count,
                'arms_path':      arms_rel,
                'suggested_type': self._suggest_item_type(mdl_path, arms_rel, qc_hint=qc_hint),
            })
            bg_info = f'{len(bodygroups)} BG' if bodygroups else 'no BG'
            arms_info = f'  arms→{arms_rel}' if arms_rel else ''
            log_callback(f'[INFO] Ready: {model_name} ({bg_info}){arms_info}  [{r["modelname"]}]')

        log_callback(f'[INFO] Phase A+B complete — {len(main_records)} model(s) ready.')

        # ── Phase B: batch config dialog on main thread ───────────────────
        event = threading.Event()
        configs_holder = [None]

        def _show_dialog():
            configs_holder[0] = self.show_batch_config_dialog(model_data_list)
            event.set()

        self.root.after(0, _show_dialog)
        event.wait()

        configs = configs_holder[0]
        if configs is None:
            log_callback('[INFO] Batch configuration cancelled.')
            return False

        # ── Phase C: write Lua for confirmed configs ──────────────────────
        log_callback(f'[INFO] Phase C — Generating Lua for {len(configs)} model(s)...')
        for config in configs:
            mdl_path   = config['mdl_path']
            model_name = os.path.basename(mdl_path)
            log_callback(f"[INFO] Generating: {config['name']} ({config['type']}, {config['price']} pts)")
            if self.skip_lua.get():
                log_callback('[INFO] Lua generation skipped (skip_lua flag set)')
            else:
                raw_reserved = config.get('reserved_for')
                if raw_reserved and ',' in raw_reserved:
                    reserved_for = [s.strip() for s in raw_reserved.split(',') if s.strip()]
                else:
                    reserved_for = raw_reserved or None
                write_pointshop_lua(
                    mdl_path,
                    config['bodygroups'],
                    output_dir,
                    log_callback,
                    item_type=config['type'],
                    arms_model=config.get('arms_path'),
                    skin_count=config['skin_count'],
                    use_color2_proxy=config['use_color2_proxy'],
                    reserved_for=reserved_for,
                    price=config['price'],
                    item_name=config['name'],
                    class_name=config.get('class_name'),
                    hidden=config.get('hidden', False),
                )
                log_callback(f'[SUCCESS] Lua generated for {model_name}')
                if config['type'] in _PM_TYPES:
                    stem = os.path.splitext(model_name)[0]
                    write_autorun_lua(
                        stem, mdl_path, config.get('arms_path'),
                        output_dir, log_callback
                    )

        log_callback(f'\n[DONE] Processed {len(configs)} model(s)')
        log_callback(f'[INFO] Output: {os.path.join(output_dir, "lua", "pointshop", "items")}')
        log_callback('[INFO] Drag the "lua" folder into your addon to install.')
        return True


    def fix_material_names(self):
        """
        Full automated pipeline:
          1. Pick addon content folder
          2. Find all .mdl files, decompile each one
          3. Scan SMDs for invalid material names, build name_map
          4. Confirm with user
          5. Rename VMT/VTF, rewrite SMD/QC, recompile, copy back
        """
        start_dir = self.output_dir.get() or os.getcwd()
        folder = filedialog.askdirectory(
            title='Select extracted addon content folder (source — will not be modified)',
            initialdir=start_dir,
        )
        if not folder:
            return

        out_folder = filedialog.askdirectory(
            title='Select output folder for fixed files',
            initialdir=os.path.dirname(folder),
        )
        if not out_folder:
            return

        crowbarcli_path = self.crowbarcli_path.get()
        studiomdl_path  = self.studiomdl_path.get()
        steam_path      = self.steam_path.get()

        if not crowbarcli_path or not os.path.isfile(crowbarcli_path):
            messagebox.showerror('Fix Material Names',
                'CrowbarCLI path is not set or invalid. Configure it in Settings.')
            return
        if not studiomdl_path or not os.path.isfile(studiomdl_path):
            messagebox.showerror('Fix Material Names',
                'studiomdl.exe path is not set or invalid. Configure it in Settings.')
            return

        game_dir = default_game_dir(steam_path)
        if not game_dir or not os.path.isdir(game_dir):
            messagebox.showerror('Fix Material Names',
                f'GarrysMod garrysmod folder not found under Steam path:\n{steam_path}\n\n'
                'Set the correct Steam path in Settings.')
            return


        def run():
            self._append_log(f'\n[MATFIX] Scanning: {folder}')

            # ── Phase 1: find all .mdl files ─────────────────────────────
            mdl_files = []
            for root_dir, _dirs, files in os.walk(folder):
                for fname in files:
                    if fname.lower().endswith('.mdl'):
                        mdl_files.append(os.path.join(root_dir, fname))

            if not mdl_files:
                self._append_log('[MATFIX] No .mdl files found.')
                return

            self._append_log(f'[MATFIX] Found {len(mdl_files)} .mdl file(s). Decompiling...')

            folder_abs = os.path.abspath(folder)

            def find_addon_root(mdl_path):
                """Walk up from mdl_path to find the nearest ancestor with a materials/ subdir."""
                d = os.path.dirname(os.path.abspath(mdl_path))
                while d != folder_abs and d.startswith(folder_abs):
                    if os.path.isdir(os.path.join(d, 'materials')):
                        return d
                    parent = os.path.dirname(d)
                    if parent == d:
                        break
                    d = parent
                return folder

            def clean_rel_path(rel):
                parts = rel.replace('\\', '/').split('/')
                cleaned = [clean_name(p).lower() for p in parts if p]
                return os.path.join(*cleaned) if cleaned else ''

            # ── Phase 2: decompile each MDL, collect bad names ────────────
            model_infos = []
            all_bad: dict[str, str] = {}

            for mdl_path in mdl_files:
                mdl_stem = os.path.splitext(os.path.basename(mdl_path))[0]
                crowbar_out = os.path.join(folder, '_matfix_work', mdl_stem)
                decompile_mdl(mdl_path, crowbarcli_path, crowbar_out, log, quiet=True)

                qc_path = self.find_qc_file(crowbar_out)
                cdmat_paths = parse_qc_cdmaterials(qc_path) if qc_path else []

                all_names, bad_set, smd_paths, _ = scan_decompiled(crowbar_out)
                name_map = {n: clean_name(n).lower() for n in bad_set}
                all_bad.update(name_map)

                if name_map:
                    self._append_log(f'[MATFIX] {mdl_stem}: {len(name_map)} bad name(s) → '
                        + ', '.join(f'"{k}"→"{v}"' for k, v in name_map.items()))
                else:
                    self._append_log(f'[MATFIX] {mdl_stem}: no bad material names')

                model_infos.append({
                    'mdl_path':    mdl_path,
                    'mdl_stem':    mdl_stem,
                    'crowbar_out': crowbar_out,
                    'qc_path':     qc_path,
                    'smd_paths':   smd_paths,
                    'name_map':    name_map,
                    'cdmat_paths': cdmat_paths,
                    'addon_root':  find_addon_root(mdl_path),
                })

            dirty = [m for m in model_infos if m['name_map']]
            if not dirty:
                self._append_log('[MATFIX] All material names are clean — nothing to fix.')
                import shutil
                shutil.rmtree(os.path.join(folder, '_matfix_work'), ignore_errors=True)
                return

            # Count all material files across dirty models' cdmat directories
            n_mat_files = 0
            _seen_count_dirs: set[str] = set()
            for info in dirty:
                for cdmat in (info['cdmat_paths'] or ['']):
                    d = os.path.join(info['addon_root'], 'materials', cdmat.strip().rstrip('/\\'))
                    if os.path.isdir(d) and d not in _seen_count_dirs:
                        _seen_count_dirs.add(d)
                        n_mat_files += sum(
                            1 for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))
                        )

            # ── Phase 3: confirm with user ────────────────────────────────
            n_models = len(dirty)
            n_smd    = sum(len(m['smd_paths']) for m in dirty)

            event   = threading.Event()
            proceed = [False]

            def _ask():
                proceed[0] = messagebox.askyesno(
                    'Fix Material Names',
                    f'{n_models} model(s) have bad material names.\n\n'
                    f'• {n_mat_files} material file(s) to copy (full cdmat directories)\n'
                    f'• {n_smd} SMD file(s) to rewrite (in temp work dir)\n'
                    f'• {n_models} MDL(s) to recompile\n\n'
                    f'Fixed files will be written to:\n{out_folder}\n\n'
                    'Source folder will not be modified. Continue?'
                )
                event.set()

            self.root.after(0, _ask)
            event.wait()

            if not proceed[0]:
                self._append_log('[MATFIX] Cancelled.')
                import shutil
                shutil.rmtree(os.path.join(folder, '_matfix_work'), ignore_errors=True)
                return

            # ── Phase 4: apply fixes ──────────────────────────────────────
            import shutil

            # 4a. Copy ALL material files from each dirty model's cdmat directories.
            # When $cdmaterials is renamed (e.g. "super masha" → "super_masha"), the
            # compiled MDL looks for every material at the new location — including
            # clean-named ones. Copy the whole directory, not just the bad-named files.
            copied_mat = 0
            _bad_chars_re = re.compile(r'[^a-zA-Z0-9_\-./\\]')
            seen_mat_dirs: set[str] = set()
            for info in dirty:
                for cdmat in (info['cdmat_paths'] or ['']):
                    src_mat_dir = os.path.join(
                        info['addon_root'], 'materials', cdmat.strip().rstrip('/\\')
                    )
                    if not os.path.isdir(src_mat_dir) or src_mat_dir in seen_mat_dirs:
                        continue
                    seen_mat_dirs.add(src_mat_dir)
                    rel_mat_dir = os.path.relpath(src_mat_dir, folder)
                    out_mat_dir = os.path.join(out_folder, clean_rel_path(rel_mat_dir))
                    os.makedirs(out_mat_dir, exist_ok=True)
                    for fname in os.listdir(src_mat_dir):
                        src_file = os.path.join(src_mat_dir, fname)
                        if not os.path.isfile(src_file):
                            continue
                        stem, ext = os.path.splitext(fname)
                        clean_stem = info['name_map'].get(stem, clean_name(stem).lower())
                        out_fname = clean_stem + ext.lower()
                        out_file = os.path.join(out_mat_dir, out_fname)
                        try:
                            shutil.copy2(src_file, out_file)
                            self._append_log(f'[MATFIX] {fname} → {out_fname}')
                            copied_mat += 1
                        except OSError as e:
                            self._append_log(f'[MATFIX WARN] Could not copy {fname}: {e}')
                            continue
                        if ext.lower() == '.vmt':
                            try:
                                with open(out_file, 'r', encoding='utf-8', errors='replace') as f:
                                    vmt_content = f.read()
                                def _fix_quoted(m):
                                    val = m.group(1)
                                    return f'"{clean_rel_path(val)}"' if _bad_chars_re.search(val) else m.group(0)
                                new_content = re.sub(r'"([^"]+)"', _fix_quoted, vmt_content)
                                if new_content != vmt_content:
                                    with open(out_file, 'w', encoding='utf-8', newline='\n') as f:
                                        f.write(new_content)
                            except OSError as e:
                                self._append_log(f'[MATFIX WARN] VMT content rewrite failed: {e}')
            renamed = copied_mat

            recompiled = 0
            skipped    = 0

            for info in dirty:
                name_map  = info['name_map']
                qc_path   = info['qc_path']
                mdl_stem  = info['mdl_stem']

                # 4b. Rewrite SMD material refs
                for smd_path in info['smd_paths']:
                    rewrite_smd_materials(smd_path, name_map)
                    self._append_log(f'[MATFIX] Rewrote SMD: {os.path.basename(smd_path)}')

                # 4c. Rewrite QC $texturegroup
                if qc_path:
                    rewrite_qc_texturegroup(qc_path, name_map)
                    self._append_log(f'[MATFIX] Rewrote QC: {os.path.basename(qc_path)}')

                # 4c-ii. Rewrite $cdmaterials if any path component has bad chars.
                # The compiled MDL embeds the cdmaterials string at compile time,
                # so this must be fixed before recompile.
                if qc_path:
                    cdmat_map = {}
                    for cdmat in (info['cdmat_paths'] or []):
                        raw = cdmat.strip().rstrip('/\\')
                        cleaned = clean_rel_path(raw)
                        if cleaned != raw:
                            cdmat_map[raw] = cleaned
                    if cdmat_map:
                        rewrite_qc_cdmaterials(qc_path, cdmat_map)
                        self._append_log(f'[MATFIX] Rewrote $cdmaterials in: {os.path.basename(qc_path)}')

                # 4c-iii. Remove duplicate $animation/$sequence blocks.
                if qc_path:
                    if deduplicate_qc_animations(qc_path, log):
                        self._append_log(f'[QC DEDUP] Cleaned duplicate animations in: {os.path.basename(qc_path)}')

                # 4d. Recompile
                if not qc_path:
                    self._append_log(f'[MATFIX WARN] No QC found for {mdl_stem} — skipping recompile')
                    skipped += 1
                    continue

                compiled_mdl = compile_qc(studiomdl_path, qc_path, game_dir, log)
                if not compiled_mdl:
                    self._append_log(f'[MATFIX WARN] Recompile failed for {mdl_stem}')
                    skipped += 1
                    continue

                # 4e. Copy compiled MDL + companions to output folder,
                #     cleaning all path components for FastDL/Unix compatibility.
                rel_mdl_dir = os.path.relpath(os.path.dirname(info['mdl_path']), folder)
                dest_dir = os.path.join(out_folder, clean_rel_path(rel_mdl_dir))
                os.makedirs(dest_dir, exist_ok=True)
                base = os.path.splitext(compiled_mdl)[0]
                companions = [compiled_mdl]
                for ext in ('.vvd', '.dx90.vtx', '.dx80.vtx', '.sw.vtx', '.phy'):
                    p = base + ext
                    if os.path.isfile(p):
                        companions.append(p)
                copy_ok = True
                for src in companions:
                    clean_fname = clean_name(os.path.basename(src)).lower()
                    try:
                        shutil.copy2(src, os.path.join(dest_dir, clean_fname))
                        self._append_log(f'[COPY] {clean_fname} → {clean_rel_path(rel_mdl_dir)}')
                    except OSError as e:
                        self._append_log(f'[MATFIX WARN] Copy failed: {e}')
                        copy_ok = False
                if copy_ok:
                    recompiled += 1
                else:
                    skipped += 1

            # Cleanup temp work dir
            shutil.rmtree(os.path.join(folder, '_matfix_work'), ignore_errors=True)

            self._append_log(f'\n[MATFIX] Done — {renamed} material file(s) copied, '
                f'{recompiled} model(s) recompiled, {skipped} skipped.')

            # ── Phase 5: optional apply to destination ────────────────────
            # Copies the output folder into a user-chosen destination and
            # removes the old bad-named files/dirs that were superseded.
            apply_event = threading.Event()
            apply_dest  = [None]

            def _ask_apply():
                if messagebox.askyesno(
                    'Apply to server folder?',
                    f'Fixed files are in:\n{out_folder}\n\n'
                    'Apply them to another folder now?\n'
                    'New files will be copied in and old bad-named\n'
                    'files/directories will be removed.',
                ):
                    d = filedialog.askdirectory(
                        title='Select destination (e.g. FastDL content folder)',
                        initialdir=os.path.dirname(out_folder),
                    )
                    apply_dest[0] = d or None
                apply_event.set()

            self.root.after(0, _ask_apply)
            apply_event.wait()

            if apply_dest[0]:
                dest = apply_dest[0]
                self._append_log(f'\n[APPLY] Copying output → {dest}')

                # Copy every file in out_folder into dest (same relative tree)
                for root_dir, _dirs, files in os.walk(out_folder):
                    for fname in files:
                        src = os.path.join(root_dir, fname)
                        rel = os.path.relpath(src, out_folder)
                        dst = os.path.join(dest, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                            self._append_log(f'[APPLY] +  {rel}')
                        except OSError as e:
                            self._append_log(f'[APPLY WARN] Copy failed {rel}: {e}')

                # Remove old bad-named files/dirs from dest
                for info in dirty:
                    # Old MDL + companion files (individual files, not whole dir)
                    orig_mdl_in_dest = os.path.join(
                        dest, os.path.relpath(info['mdl_path'], folder)
                    )
                    orig_base = os.path.splitext(orig_mdl_in_dest)[0]
                    for ext in ('.mdl', '.vvd', '.dx90.vtx', '.dx80.vtx', '.sw.vtx', '.phy'):
                        old_f = orig_base + ext
                        if os.path.isfile(old_f):
                            os.remove(old_f)
                            self._append_log(f'[APPLY] -  {os.path.relpath(old_f, dest)}')
                    # Remove the old MDL directory entirely (may still have files
                    # if path was renamed, e.g. "super masha/" → "super_masha/")
                    old_mdl_dir = os.path.dirname(orig_mdl_in_dest)
                    if os.path.isdir(old_mdl_dir):
                        shutil.rmtree(old_mdl_dir)
                        self._append_log(f'[APPLY] -  (dir) {os.path.relpath(old_mdl_dir, dest)}')

                    # Old bad-named VMT/VTF files
                    for bad, _clean in info['name_map'].items():
                        for cdmat in (info['cdmat_paths'] or ['']):
                            rel_mat = os.path.relpath(
                                os.path.join(
                                    info['addon_root'], 'materials',
                                    cdmat.strip().rstrip('/\\')
                                ),
                                folder,
                            )
                            old_mat_dir = os.path.join(dest, rel_mat)
                            for ext in ('.vmt', '.vtf'):
                                old_f = os.path.join(old_mat_dir, bad + ext)
                                if os.path.isfile(old_f):
                                    os.remove(old_f)
                                    self._append_log(f'[APPLY] -  {os.path.relpath(old_f, dest)}')

                    # If the cdmat directory was renamed, remove the old dir entirely
                    for cdmat in (info['cdmat_paths'] or ['']):
                        raw = cdmat.strip().rstrip('/\\')
                        if clean_rel_path(raw) != raw:
                            rel_old = os.path.relpath(
                                os.path.join(info['addon_root'], 'materials', raw),
                                folder,
                            )
                            old_dir = os.path.join(dest, rel_old)
                            if os.path.isdir(old_dir):
                                shutil.rmtree(old_dir)
                                self._append_log(f'[APPLY] -  (dir) {os.path.relpath(old_dir, dest)}')

                self._append_log(f'[APPLY] Done.')

        threading.Thread(target=run, daemon=True).start()

    # ── Addon Cleaner ────────────────────────────────────────────────────
    def clean_addon(self):
        """
        Build the configured model namespace/<creator>/<addon>/ skeleton then process each MDL:
        decompile → patch QC paths → recompile → copy output + materials.
        """
        crowbarcli_path = self.crowbarcli_path.get()
        studiomdl_path  = self.studiomdl_path.get()
        steam_path      = self.steam_path.get()
        model_namespace = self.model_namespace.get()

        if not crowbarcli_path or not os.path.isfile(crowbarcli_path):
            messagebox.showerror('Addon Cleaner',
                'CrowbarCLI path not set or invalid. Configure it in Settings.')
            return
        if not studiomdl_path or not os.path.isfile(studiomdl_path):
            messagebox.showerror('Addon Cleaner',
                'studiomdl.exe not set or invalid. Configure it in Settings.')
            return
        game_dir = default_game_dir(steam_path)
        if not game_dir or not os.path.isdir(game_dir):
            messagebox.showerror('Addon Cleaner',
                f'GarrysMod folder not found under Steam path:\n{steam_path}\n\n'
                'Set the correct Steam path in Settings.')
            return

        # ── Dialog ───────────────────────────────────────────────────────
        dlg = tk.Toplevel(self.root)
        dlg.title('Addon Cleaner')
        dlg.configure(bg=self.BG)
        dlg.transient(self.root)
        dlg.geometry('1100x720')
        dlg.resizable(True, True)

        def _detect_from_path(path, kw_dict):
            """Return the first matching value from kw_dict whose key appears in path."""
            path_lower = path.replace('\\', '/').lower()
            for keyword, value in kw_dict.items():
                if keyword.lower() in path_lower:
                    return value
            return None

        def _browse_var(var, title):
            d = filedialog.askdirectory(title=title, initialdir=var.get() or os.getcwd())
            if d:
                var.set(d)

        # ── Input fields ─────────────────────────────────────────────────
        top = self._frame(dlg)
        top.pack(fill='x', padx=14, pady=(10, 4))

        staging_var = tk.StringVar(value=self._cleaner_staging)
        creator_var = tk.StringVar(value=self._cleaner_creator)
        addon_var   = tk.StringVar(value=self._cleaner_addon)
        output_var  = tk.StringVar(value=self._cleaner_output)

        # Write back to instance vars whenever they change
        staging_var.trace_add('write', lambda *_: setattr(self, '_cleaner_staging', staging_var.get()))
        output_var .trace_add('write', lambda *_: setattr(self, '_cleaner_output',  output_var.get()))
        creator_var.trace_add('write', lambda *_: setattr(self, '_cleaner_creator', creator_var.get()))
        addon_var  .trace_add('write', lambda *_: setattr(self, '_cleaner_addon',   addon_var.get()))

        for label, var, browse_title in [
            ('Staging folder', staging_var, 'Select staging folder (addon files to clean)'),
            ('Output folder',  output_var,  'Select output folder for cleaned files'),
        ]:
            rf = self._frame(top)
            rf.pack(fill='x', pady=2)
            self._label(rf, label, width=14, anchor='w').pack(side='left')
            self._entry(rf, var, width=48).pack(side='left', padx=(4, 4))
            self._button(rf, 'Browse', lambda v=var, t=browse_title: _browse_var(v, t),
                         bg=self.BG, fg=self.FG).pack(side='left')

        dfl_row = self._frame(top)
        dfl_row.pack(fill='x', pady=2)
        self._label(dfl_row, 'Default creator', width=14, anchor='w').pack(side='left')
        self._entry(dfl_row, creator_var, width=22).pack(side='left', padx=(4, 12))
        self._label(dfl_row, 'Default addon', anchor='w').pack(side='left')
        self._entry(dfl_row, addon_var, width=22).pack(side='left', padx=(4, 0))
        self._label(dfl_row, '← pre-fills rows on Scan', fg='#666666',
                    font=('Segoe UI', 8)).pack(side='left', padx=(8, 0))

        def _show_cleaner_keyword_editor():
            pop = tk.Toplevel(dlg)
            pop.title('Path Auto-detect Keywords')
            pop.configure(bg=self.BG)
            pop.transient(dlg)
            pop.resizable(False, False)

            self._label(pop, 'Keywords matched against each MDL file path on Scan (case-insensitive)',
                        fg='#999999', font=('Segoe UI', 9)).pack(anchor='w', padx=14, pady=(10, 2))

            def _make_section(parent, title, kw_dict):
                self._label(parent, title, font=self.FONT_BOLD).pack(anchor='w', padx=14, pady=(8, 2))
                lf = self._frame(parent)
                lf.pack(fill='x', padx=14, pady=2)
                hf = self._frame(lf)
                hf.pack(fill='x')
                self._label(hf, 'Keyword', width=22, font=self.FONT_BOLD, anchor='w').pack(side='left')
                self._label(hf, 'Auto-fill value', width=22, font=self.FONT_BOLD, anchor='w').pack(side='left')
                ttk.Separator(lf, orient='horizontal').pack(fill='x', pady=(2, 4))

                kw_canvas2    = tk.Canvas(lf, bg=self.BG, highlightthickness=0, height=120)
                kw_scroll2    = ttk.Scrollbar(lf, orient='vertical', command=kw_canvas2.yview)
                kw_scrollable2 = self._frame(kw_canvas2)
                kw_scrollable2.bind('<Configure>', lambda e: kw_canvas2.configure(
                    scrollregion=kw_canvas2.bbox('all')))
                kw_canvas2.create_window((0, 0), window=kw_scrollable2, anchor='nw')
                kw_canvas2.configure(yscrollcommand=kw_scroll2.set)
                kw_canvas2.pack(side='left', fill='both', expand=True)
                kw_scroll2.pack(side='right', fill='y')

                kw_rows2 = []

                def _refresh(kd=kw_dict, sc=kw_scrollable2, kr=kw_rows2):
                    for w in sc.winfo_children():
                        w.destroy()
                    kr.clear()
                    for kw, val in list(kd.items()):
                        rf2 = self._frame(sc)
                        rf2.pack(fill='x', pady=1)
                        kw_var2  = tk.StringVar(value=kw)
                        val_var2 = tk.StringVar(value=val)
                        self._entry(rf2, kw_var2,  width=22).pack(side='left', padx=(0, 6))
                        self._entry(rf2, val_var2, width=22).pack(side='left')
                        kr.append((kw_var2, val_var2, rf2))

                _refresh()

                af = self._frame(parent)
                af.pack(fill='x', padx=14, pady=(4, 2))
                new_kw2  = tk.StringVar()
                new_val2 = tk.StringVar()
                self._label(af, 'Keyword:', anchor='w').pack(side='left')
                self._entry(af, new_kw2,  width=14).pack(side='left', padx=(4, 6))
                self._label(af, '→', fg='#999999').pack(side='left')
                self._entry(af, new_val2, width=14).pack(side='left', padx=(4, 6))

                def _add(kd=kw_dict, nk=new_kw2, nv=new_val2, rf=_refresh):
                    k, v = nk.get().strip().lower(), nv.get().strip()
                    if k and v:
                        kd[k] = v
                        nk.set('')
                        nv.set('')
                        rf()

                def _remove_last(kd=kw_dict, kr=kw_rows2, rf=_refresh):
                    if kr:
                        k = kr[-1][0].get().strip().lower()
                        kd.pop(k, None)
                        rf()

                self._button(af, '+ Add',       _add,         bg=self.ACCENT, fg='#ffffff').pack(side='left')
                self._button(af, '− Remove last', _remove_last, bg=self.BG,     fg=self.FG).pack(side='left', padx=(6, 0))

                return kw_rows2

            creator_rows = _make_section(pop, 'Creator keywords', self.cleaner_creator_keywords)
            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))
            addon_rows   = _make_section(pop, 'Addon keywords',   self.cleaner_addon_keywords)

            def _save_and_close():
                new_c = {}
                for kv, vv, _ in creator_rows:
                    k, v = kv.get().strip().lower(), vv.get().strip()
                    if k and v:
                        new_c[k] = v
                new_a = {}
                for kv, vv, _ in addon_rows:
                    k, v = kv.get().strip().lower(), vv.get().strip()
                    if k and v:
                        new_a[k] = v
                self.cleaner_creator_keywords = new_c
                self.cleaner_addon_keywords   = new_a
                save_cleaner_keywords(new_c, new_a)
                pop.destroy()

            ttk.Separator(pop, orient='horizontal').pack(fill='x', padx=14, pady=(8, 2))
            bf = self._frame(pop)
            bf.pack(padx=14, pady=(4, 10))
            self._button(bf, 'Save & Close', _save_and_close,
                         bg=self.ACCENT, fg='#ffffff').pack(side='left', padx=(0, 8))
            self._button(bf, 'Cancel', pop.destroy, bg=self.BG, fg=self.FG).pack(side='left')
            pop.update_idletasks()
            pop.geometry(f'500x{min(pop.winfo_reqheight(), 600)}')

        self._button(dfl_row, 'Path Keywords…', _show_cleaner_keyword_editor,
                     bg=self.BG, fg=self.FG).pack(side='left', padx=(12, 0))

        # ── Texture size clamp controls ───────────────────────────────────
        _POW2_CHOICES = ['No limit', '32', '64', '128', '256', '512', '1024', '2048', '4096']
        tex_row = self._frame(top)
        tex_row.pack(fill='x', pady=2)
        self._label(tex_row, 'Max tex width', width=14, anchor='w').pack(side='left')
        _init_w = str(self.max_tex_w.get()) if self.max_tex_w.get() > 0 else 'No limit'
        max_w_var = tk.StringVar(value=_init_w)
        ttk.Combobox(tex_row, textvariable=max_w_var, values=_POW2_CHOICES,
                     width=10, state='readonly').pack(side='left', padx=(4, 16))
        self._label(tex_row, 'Max tex height', anchor='w').pack(side='left')
        _init_h = str(self.max_tex_h.get()) if self.max_tex_h.get() > 0 else 'No limit'
        max_h_var = tk.StringVar(value=_init_h)
        ttk.Combobox(tex_row, textvariable=max_h_var, values=_POW2_CHOICES,
                     width=10, state='readonly').pack(side='left', padx=(4, 0))
        self._label(tex_row, '(0 = no clamp, requires VTFCmd in Settings)',
                    fg='#666666', font=('Segoe UI', 8)).pack(side='left', padx=(8, 0))

        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(6, 2))

        # ── Preview table ─────────────────────────────────────────────────
        tbl_frame = self._frame(dlg)
        tbl_frame.pack(fill='both', expand=True, padx=14, pady=4)

        col_hdr = self._frame(tbl_frame)
        col_hdr.pack(fill='x')
        for txt, w in [('Source MDL path', 42), ('Creator', 18), ('Addon', 18), ('Type', 8), ('KB', 5)]:
            self._label(col_hdr, txt, width=w, font=self.FONT_BOLD, anchor='w').pack(side='left', padx=(0, 4))
        ttk.Separator(tbl_frame, orient='horizontal').pack(fill='x', pady=(2, 2))

        tbl_canvas = tk.Canvas(tbl_frame, bg=self.BG, highlightthickness=0)
        tbl_scroll = ttk.Scrollbar(tbl_frame, orient='vertical', command=tbl_canvas.yview)
        tbl_inner  = self._frame(tbl_canvas)
        tbl_inner.bind('<Configure>', lambda e: tbl_canvas.configure(
            scrollregion=tbl_canvas.bbox('all')))
        tbl_canvas.create_window((0, 0), window=tbl_inner, anchor='nw')
        tbl_canvas.configure(yscrollcommand=tbl_scroll.set)
        tbl_canvas.pack(side='left', fill='both', expand=True)
        tbl_scroll.pack(side='right', fill='y')

        ttk.Separator(dlg, orient='horizontal').pack(fill='x', padx=14, pady=(2, 0))

        # ── Log widget ────────────────────────────────────────────────────
        log_frame = self._frame(dlg)
        log_frame.pack(fill='x', padx=14, pady=(4, 0))
        log_box = tk.Text(log_frame, height=8, bg=self.SURFACE, fg=self.FG,
                          font=('Consolas', 8), state='disabled', wrap='none')
        log_sb = ttk.Scrollbar(log_frame, orient='vertical', command=log_box.yview)
        log_box.configure(yscrollcommand=log_sb.set)
        log_box.pack(side='left', fill='both', expand=True)
        log_sb.pack(side='right', fill='y')

        # ── Button bar ────────────────────────────────────────────────────
        btn_bar = self._frame(dlg)
        btn_bar.pack(fill='x', padx=14, pady=(4, 10))

        scan_rows = []  # list of {mdl_path, size, type_var}
        qc_cache  = {}  # mdl_path → {qc_path, signals, crowbar_outdir}

        def _build_out_path(mdl_path, type_label, creator, addon):
            stem = os.path.splitext(os.path.basename(mdl_path))[0]
            c = clean_name(creator).lower()
            a = clean_name(addon).lower()
            if type_label == 'Arms':
                return f'models/gemboi/{c}/{a}/c_arms/{stem}.mdl'
            return f'models/gemboi/{c}/{a}/{stem}.mdl'

        def do_scan():
            staging = staging_var.get().strip()
            if not staging or not os.path.isdir(staging):
                messagebox.showerror('Addon Cleaner', 'Set a valid staging folder first.')
                return

            for w in tbl_inner.winfo_children():
                w.destroy()
            scan_rows.clear()

            staging_abs = os.path.abspath(staging)
            mdl_files = []
            for root_d, _dirs, files in os.walk(staging_abs):
                for fname in files:
                    if not fname.lower().endswith('.mdl'):
                        continue
                    full = os.path.join(root_d, fname)
                    rel  = os.path.relpath(full, staging_abs).replace('\\', '/')
                    if rel.lower().startswith('models/gemboi/'):
                        continue
                    if 'npc' in rel.lower().split('/'):
                        continue
                    mdl_files.append(full)

            if not mdl_files:
                self._append_log('[SCAN] No non-gemboi .mdl files found in staging folder.')
                return

            # ── Decompile all, build QC cache ────────────────────────────
            self._append_log(f'[SCAN] Decompiling {len(mdl_files)} model(s)...')
            qc_cache.clear()
            for idx, mdl_path in enumerate(mdl_files):
                mdl_stem       = os.path.splitext(os.path.basename(mdl_path))[0]
                crowbar_outdir = os.path.join(staging_abs, '_clean_work',
                                              f'{idx:04d}_{mdl_stem}')
                decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, _log, quiet=True)
                qc_path = self.find_qc_file(crowbar_outdir)
                signals = parse_qc_type_signals(qc_path) if qc_path else None
                qc_cache[mdl_path] = {
                    'qc_path':        qc_path,
                    'signals':        signals,
                    'crowbar_outdir': crowbar_outdir,
                }

            dfl_creator = creator_var.get().strip()
            dfl_addon   = addon_var.get().strip()

            for mdl_path in mdl_files:
                cached     = qc_cache[mdl_path]
                signals    = cached['signals']
                type_label = 'Arms' if (signals and signals['has_c_arms_include']) else 'Main'
                size_kb    = os.path.getsize(mdl_path) // 1024
                rel_src      = os.path.relpath(mdl_path, staging_abs).replace('\\', '/')

                _det_c = _detect_from_path(mdl_path, self.cleaner_creator_keywords) or dfl_creator
                _det_a = _detect_from_path(mdl_path, self.cleaner_addon_keywords)   or dfl_addon
                row_creator = tk.StringVar(value=_det_c)
                row_addon   = tk.StringVar(value=_det_a)
                type_var    = tk.StringVar(value=type_label)

                # ── Two-line row ─────────────────────────────────────────
                outer = self._frame(tbl_inner)
                outer.pack(fill='x', pady=2)

                # Line 1: full source path + size
                line1 = self._frame(outer)
                line1.pack(fill='x')
                self._label(line1, rel_src, anchor='w',
                            fg='#aaaaaa', font=('Consolas', 8)).pack(side='left', padx=(0, 6))
                self._label(line1, f'{size_kb} KB', fg='#555555',
                            font=('Segoe UI', 8)).pack(side='right')

                # Line 2: creator | addon | type | → output preview
                line2 = self._frame(outer)
                line2.pack(fill='x')
                self._label(line2, 'Creator:', anchor='w',
                            font=('Segoe UI', 8)).pack(side='left')
                c_ent = self._entry(line2, row_creator, width=20)
                c_ent.pack(side='left', padx=(2, 8))
                self._label(line2, 'Addon:', anchor='w',
                            font=('Segoe UI', 8)).pack(side='left')
                a_ent = self._entry(line2, row_addon, width=20)
                a_ent.pack(side='left', padx=(2, 8))
                ttk.Combobox(line2, textvariable=type_var, values=['Main', 'Arms', 'Skip'],
                             state='readonly', width=7, font=self.FONT).pack(side='left', padx=(0, 8))
                out_lbl = self._label(line2,
                                      _build_out_path(mdl_path, type_label, dfl_creator, dfl_addon),
                                      anchor='w', fg='#66aaff', font=('Segoe UI', 8))
                out_lbl.pack(side='left')

                def _wire(tv, cv, av, mp, lbl, ce, ae):
                    def _update(*_):
                        is_skip = tv.get() == 'Skip'
                        ce.config(state='disabled' if is_skip else 'normal',
                                  bg='#2a2a2a' if is_skip else self.SURFACE)
                        ae.config(state='disabled' if is_skip else 'normal',
                                  bg='#2a2a2a' if is_skip else self.SURFACE)
                        lbl.config(text='' if is_skip else _build_out_path(mp, tv.get(), cv.get(), av.get()))
                    tv.trace_add('write', _update)
                    cv.trace_add('write', _update)
                    av.trace_add('write', _update)
                    _update()  # apply initial state
                _wire(type_var, row_creator, row_addon, mdl_path, out_lbl, c_ent, a_ent)

                ttk.Separator(tbl_inner, orient='horizontal').pack(fill='x', pady=(2, 0))
                scan_rows.append({'mdl_path': mdl_path, 'type_var': type_var,
                                  'creator_var': row_creator, 'addon_var': row_addon})

            self._append_log(f'[SCAN] Found {len(mdl_files)} MDL(s). Fill creator/addon per row, then Build & Clean.')

        def do_build():
            staging = staging_var.get().strip()
            output  = output_var.get().strip()

            active = [r for r in scan_rows if r['type_var'].get() != 'Skip']
            if not active:
                messagebox.showinfo('Addon Cleaner', 'No models to process (all skipped).')
                return
            if any(not r['creator_var'].get().strip() or not r['addon_var'].get().strip()
                   for r in active):
                messagebox.showerror('Addon Cleaner',
                    'Every active row needs a creator and addon name.')
                return
            if not output or not os.path.isdir(os.path.dirname(output) or '.'):
                messagebox.showerror('Addon Cleaner', 'Set a valid output folder.')
                return

            build_btn.config(state='disabled')
            scan_btn.config(state='disabled')

            vtfcmd_path = self.vtfcmd_path.get()
            max_w = 0 if max_w_var.get() == 'No limit' else int(max_w_var.get())
            max_h = 0 if max_h_var.get() == 'No limit' else int(max_h_var.get())
            # Persist the chosen values back to config
            self.max_tex_w.set(max_w)
            self.max_tex_h.set(max_h)
            save_last_paths(
                self.input_type.get(), self.input_paths,
                self.output_dir.get(), self.write_bodygroups.get(),
                self.steamcmd_path.get(), self.crowbarcli_path.get(),
                self.game_choice.get(), self.steam_path.get(),
                self.studiomdl_path.get(), vtfcmd_path, max_w, max_h)

            def run():
                import shutil
                staging_abs = os.path.abspath(staging)

                # ── Step 1: build skeletons for all unique (creator, addon) pairs ──
                seen_skeletons: set[tuple] = set()
                for row in active:
                    c = clean_name(row['creator_var'].get().strip()).lower()
                    a = clean_name(row['addon_var'].get().strip()).lower()
                    if (c, a) in seen_skeletons:
                        continue
                    seen_skeletons.add((c, a))
                    has_arms_for = any(
                        r['type_var'].get() == 'Arms'
                        and clean_name(r['creator_var'].get().strip()).lower() == c
                        and clean_name(r['addon_var'].get().strip()).lower() == a
                        for r in active
                    )
                    os.makedirs(os.path.join(output, 'models', model_namespace, c, a), exist_ok=True)
                    if has_arms_for:
                        os.makedirs(os.path.join(output, 'models', model_namespace, c, a, 'c_arms'), exist_ok=True)
                    os.makedirs(os.path.join(output, 'materials', 'models', model_namespace, c, a), exist_ok=True)
                self._append_log(f'[CLEAN] Skeletons created under {output}')

                # mat tracking keyed by (creator, addon)
                cdmat_by_addon: dict[tuple, set] = {}
                nameMap_by_addon: dict[tuple, dict] = {}
                expected_mats_by_addon: dict[tuple, set] = {}
                mat_sources_by_addon: dict[tuple, dict] = {}

                # ── Step 2: process each MDL ──────────────────────────────
                total_mdls = len(active)
                for mdl_idx, row in enumerate(active, 1):
                    mdl_path   = row['mdl_path']
                    mdl_stem   = os.path.splitext(os.path.basename(mdl_path))[0]
                    is_arms    = row['type_var'].get() == 'Arms'
                    creator    = clean_name(row['creator_var'].get().strip()).lower()
                    addon      = clean_name(row['addon_var'].get().strip()).lower()
                    new_mat_rel = f'models/gemboi/{creator}/{addon}'
                    work_dir   = os.path.join(staging_abs, '_clean_work', mdl_stem)

                    self._append_log(f'\n[CLEAN] [{mdl_idx}/{total_mdls}] ── {mdl_stem} ({"arms" if is_arms else "main"}) ──')

                    # Reuse decompile from scan; fall back to fresh decompile if cache miss
                    cached   = qc_cache.get(mdl_path, {})
                    work_dir = cached.get('crowbar_outdir') or work_dir
                    qc_path  = cached.get('qc_path')
                    if not qc_path:
                        self._append_log(f'[CLEAN]   decompiling (cache miss)...')
                        decompile_mdl(mdl_path, crowbarcli_path, work_dir, _log, quiet=True)
                        qc_path = self.find_qc_file(work_dir)
                    if not qc_path:
                        self._append_log(f'[CLEAN] WARN: no QC found for {mdl_stem}, skipping')
                        continue
                    self._append_log(f'[CLEAN]   QC: {os.path.basename(qc_path)}')

                    cdmat_paths = parse_qc_cdmaterials(qc_path)
                    self._append_log(f'[CLEAN]   $cdmaterials: {cdmat_paths}')
                    key = (creator, addon)
                    if key not in cdmat_by_addon:
                        cdmat_by_addon[key] = set()
                    for cp in cdmat_paths:
                        raw = cp.strip().rstrip('/\\')
                        # Try staging_abs/materials/<cdmat>
                        src_mat = os.path.join(staging_abs, 'materials', raw)
                        if not os.path.isdir(src_mat):
                            # Walk the staging folder to find any materials/<cdmat> dir
                            src_mat = None
                            self._append_log(f'[CLEAN]   searching staging for materials/{raw}...')
                            for root_d, dirs, _ in os.walk(staging_abs):
                                if os.path.basename(root_d).lower() == 'materials':
                                    candidate = os.path.join(root_d, raw)
                                    if os.path.isdir(candidate):
                                        src_mat = candidate
                                        break
                                    # Also try the materials dir itself if cdmat is empty
                                    if not raw and os.path.isdir(root_d):
                                        src_mat = root_d
                                        break
                        if src_mat and os.path.isdir(src_mat):
                            self._append_log(f'[CLEAN]   materials dir: {src_mat}')
                            cdmat_by_addon[key].add((raw, src_mat))
                        else:
                            self._append_log(f'[CLEAN]   WARN: no material dir found for "{cp}"')

                    # Build new modelname (no models/ prefix, no .mdl)
                    if is_arms:
                        new_modelname = f'gemboi/{creator}/{addon}/c_arms/{mdl_stem}'
                    else:
                        new_modelname = f'gemboi/{creator}/{addon}/{mdl_stem}'

                    # Rewrite QC
                    self._append_log(f'[CLEAN]   rewriting QC → {new_modelname}')
                    rewrite_qc_modelname(qc_path, new_modelname)
                    cdmat_map = {}
                    for cp in cdmat_paths:
                        raw = cp.strip().rstrip('/\\')
                        if raw != new_mat_rel:
                            cdmat_map[raw] = new_mat_rel
                    if cdmat_map:
                        rewrite_qc_cdmaterials(qc_path, cdmat_map)

                    # Clean bad material names in SMDs
                    self._append_log(f'[CLEAN]   scanning SMDs for bad material names...')
                    _all, bad_set, smd_paths, mat_to_smds = scan_decompiled(work_dir)
                    self._append_log(f'[CLEAN]   {len(smd_paths)} mesh SMD(s), {len(_all)} material(s), {len(bad_set)} bad name(s)')
                    name_map = {n: clean_name(n).lower() for n in bad_set}
                    if key not in nameMap_by_addon:
                        nameMap_by_addon[key] = {}
                    nameMap_by_addon[key].update(name_map)
                    if key not in expected_mats_by_addon:
                        expected_mats_by_addon[key] = set()
                    expected_mats_by_addon[key].update(name_map.get(n, n) for n in _all)
                    if key not in mat_sources_by_addon:
                        mat_sources_by_addon[key] = {}
                    for mat, smds in mat_to_smds.items():
                        cleaned = name_map.get(mat, mat)
                        mat_sources_by_addon[key].setdefault(cleaned, []).extend(smds)
                    if name_map:
                        for old_n, new_n in name_map.items():
                            self._append_log(f'[CLEAN]   rename: {old_n} → {new_n}')
                        self._append_log(f'[CLEAN]   rewriting SMDs and texturegroup...')
                        for smd in smd_paths:
                            rewrite_smd_materials(smd, name_map)
                        rewrite_qc_texturegroup(qc_path, name_map)

                    deduplicate_qc_animations(qc_path, _log)

                    # Recompile
                    self._append_log(f'[CLEAN]   recompiling with studiomdl...')
                    compiled = compile_qc(studiomdl_path, qc_path, game_dir, _log)
                    if not compiled:
                        self._append_log(f'[CLEAN]   ERROR: recompile failed for {mdl_stem}')
                        continue

                    # Copy compiled output to skeleton
                    self._append_log(f'[CLEAN]   copying compiled model files...')
                    dest_dir = os.path.join(output, 'models', 'gemboi', creator, addon,
                                            'c_arms' if is_arms else '')
                    dest_dir = dest_dir.rstrip(os.sep + '/')
                    base = os.path.splitext(compiled)[0]
                    companions = [compiled]
                    for ext in ('.vvd', '.dx90.vtx', '.dx80.vtx', '.sw.vtx', '.phy'):
                        p = base + ext
                        if os.path.isfile(p):
                            companions.append(p)
                    for src in companions:
                        dst = os.path.join(dest_dir, os.path.basename(src))
                        shutil.copy2(src, dst)
                        self._append_log(f'[CLEAN]   → {os.path.relpath(dst, output)}')
                    self._append_log(f'[CLEAN]   done ({mdl_idx}/{total_mdls})')

                # ── Step 3: copy materials per (creator, addon) ───────────
                self._append_log(f'\n[CLEAN] ── Materials ──')
                _bad_chars_re = re.compile(r'[^a-zA-Z0-9_\-./\\]')
                _SECONDARY_TEX_PARAMS = frozenset({
                    'bumpmap', 'normalmap', 'detail', 'envmapmask',
                    'lightwarptexture', 'phongexponenttexture', 'phongwarptexture',
                    'selfillummask', 'blendmodulatetexture', 'dudvmap',
                    'ambientoccltexture', 'hdrbasetexture', 'hdrcompressedtexture',
                })
                _TEX_PAIR_RE = re.compile(r'"\$([a-zA-Z0-9_]+)"(\s+)"([^"$%][^"]*)"')

                for (c, a), cdmat_set in cdmat_by_addon.items():
                    mat_dir      = os.path.join(output, 'materials', 'models', model_namespace, c, a)
                    mat_name_map = nameMap_by_addon.get((c, a), {})
                    new_mat_rel  = f'models/gemboi/{c}/{a}'
                    old_prefixes = [cp for cp, _ in cdmat_set]

                    for _cp, src_mat_dir in cdmat_set:
                        # Pre-scan VMTs to determine per-stem routing (flat vs shared).
                        # $basetexture → flat; any secondary param → shared (secondary wins conflict).
                        stem_routing: dict[str, str] = {}
                        for _pre_fname in os.listdir(src_mat_dir):
                            if not _pre_fname.lower().endswith('.vmt'):
                                continue
                            try:
                                with open(os.path.join(src_mat_dir, _pre_fname), 'r',
                                          encoding='utf-8', errors='replace') as _pf:
                                    _pre_content = _pf.read()
                            except OSError:
                                continue
                            for _pm in re.finditer(r'"\$([a-zA-Z0-9_]+)"\s+"([^"$%][^"]*)"',
                                                   _pre_content, re.IGNORECASE):
                                _pparam = _pm.group(1).lower()
                                _pval   = _pm.group(2).replace('\\', '/').rsplit('/', 1)[-1]
                                _pstem  = mat_name_map.get(_pval, clean_name(_pval).lower())
                                if _pparam == 'basetexture':
                                    stem_routing.setdefault(_pstem, 'flat')
                                elif _pparam in _SECONDARY_TEX_PARAMS:
                                    stem_routing[_pstem] = 'shared'

                        for _sub_root, _sub_dirs, _sub_files in os.walk(src_mat_dir):
                            _in_subdir = _sub_root != src_mat_dir
                            for fname in _sub_files:
                                src_file = os.path.join(_sub_root, fname)
                                ext_f = os.path.splitext(fname)[1].lower()

                                if _in_subdir and ext_f != '.vtf':
                                    continue  # only VTFs from subdirs; VMTs live at top level

                                stem_f = os.path.splitext(fname)[0]
                                clean_stem = mat_name_map.get(stem_f, clean_name(stem_f).lower())
                                out_fname  = clean_stem + ext_f

                                routing = stem_routing.get(clean_stem, 'flat') if ext_f == '.vtf' else 'flat'
                                if routing == 'shared':
                                    addon_shared_dir = os.path.join(mat_dir, 'shared')
                                    os.makedirs(addon_shared_dir, exist_ok=True)
                                    out_file = os.path.join(addon_shared_dir, out_fname)
                                else:
                                    out_file = os.path.join(mat_dir, out_fname)

                                try:
                                    shutil.copy2(src_file, out_file)
                                except OSError as e:
                                    self._append_log(f'[CLEAN] WARN: could not copy {fname}: {e}')
                                    continue
                                if ext_f == '.vtf':
                                    dims = read_vtf_dimensions(out_file)
                                    if dims:
                                        w, h = dims
                                        new_w, new_h = clamp_dimensions(w, h, max_w, max_h)
                                        if (new_w, new_h) != (w, h):
                                            if vtfcmd_path and os.path.isfile(vtfcmd_path):
                                                ok = resize_vtf(vtfcmd_path, out_file, new_w, new_h, _log)
                                                final = read_vtf_dimensions(out_file) if ok else None
                                                if ok and final:
                                                    self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)} [{w}×{h} → {final[0]}×{final[1]}]')
                                                else:
                                                    self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)} [{w}×{h}] (resize failed, kept original)')
                                            else:
                                                self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)} [{w}×{h}] WARN: over limit ({new_w}×{new_h}), VTFCmd not configured')
                                        else:
                                            self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)} [{w}×{h}]')
                                    else:
                                        self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)}')
                                else:
                                    self._append_log(f'[CLEAN] → {os.path.relpath(out_file, output)}')
                                if ext_f == '.vmt' and not _in_subdir:
                                    try:
                                        with open(out_file, 'r', encoding='utf-8', errors='replace') as f:
                                            vmt_content = f.read()
                                        def _fix_vmt(m, _old=old_prefixes, _new=new_mat_rel,
                                                     _sec=_SECONDARY_TEX_PARAMS):
                                            param = m.group(1).lower()
                                            ws    = m.group(2)
                                            val   = m.group(3).replace('\\', '/')
                                            if param == 'basetexture':
                                                target = _new
                                            elif param in _sec:
                                                target = _new + '/shared'
                                            else:
                                                return m.group(0)
                                            if val.lower().startswith('shared/'):
                                                basename = val.split('/', 1)[1].rsplit('/', 1)[-1]
                                                if _bad_chars_re.search(basename):
                                                    basename = clean_name(basename).lower()
                                                return f'"${m.group(1)}"{ws}"{_new}/shared/{basename}"'
                                            for pfx in _old:
                                                pfx_n = pfx.strip().rstrip('/\\').replace('\\', '/')
                                                if val.lower().startswith(pfx_n.lower() + '/') or \
                                                   val.lower() == pfx_n.lower():
                                                    basename = val[len(pfx_n):].lstrip('/').rsplit('/', 1)[-1]
                                                    if _bad_chars_re.search(basename):
                                                        basename = clean_name(basename).lower()
                                                    return f'"${m.group(1)}"{ws}"{target}/{basename}"'
                                            # Root-prefix fallback: handles cross-subdir refs
                                            # e.g. "models/ddlc_lp/shared/lightwarp" when cdmaterials
                                            # prefix is "models/ddlc_lp/yuri".
                                            for pfx in _old:
                                                pfx_n = pfx.strip().rstrip('/\\').replace('\\', '/')
                                                root  = pfx_n.rsplit('/', 1)[0] if '/' in pfx_n else ''
                                                if root and val.lower().startswith(root.lower() + '/'):
                                                    basename = val[len(root):].lstrip('/').rsplit('/', 1)[-1]
                                                    if _bad_chars_re.search(basename):
                                                        basename = clean_name(basename).lower()
                                                    return f'"${m.group(1)}"{ws}"{target}/{basename}"'
                                            if _bad_chars_re.search(val):
                                                return f'"${m.group(1)}"{ws}"{clean_name(val).lower()}"'
                                            return m.group(0)
                                        def _fix_chars(m):
                                            val = m.group(1)
                                            if val.startswith(('$', '%')):
                                                return m.group(0)
                                            if _bad_chars_re.search(val):
                                                return f'"{clean_name(val).lower()}"'
                                            return m.group(0)
                                        new_content = re.sub(_TEX_PAIR_RE, _fix_vmt, vmt_content)
                                        new_content = re.sub(r'"([^"]+)"', _fix_chars, new_content)
                                        if new_content != vmt_content:
                                            with open(out_file, 'w', encoding='utf-8', newline='\n') as f:
                                                f.write(new_content)
                                    except OSError as e:
                                        self._append_log(f'[CLEAN] WARN: VMT rewrite failed for {fname}: {e}')

                # ── Step 3.5: VMT texture dependency walker ──────────────────
                # Catch secondary textures (phong, lightwarp, detail, etc.) that
                # weren't directly in src_mat_dir and therefore missed by Step 3.
                self._append_log(f'[CLEAN] ── Texture dependency check ──')
                staging_vtf_index: dict[str, str] = {}
                _walked_mat_roots: set[str] = set()
                for _cdmat_set in cdmat_by_addon.values():
                    for _cp2, _smd2 in _cdmat_set:
                        # Walk up from src_mat_dir to find its materials/ parent
                        _p2 = _smd2
                        while True:
                            if os.path.basename(_p2).lower() == 'materials':
                                break
                            _par2 = os.path.dirname(_p2)
                            if _par2 == _p2:
                                _p2 = None
                                break
                            _p2 = _par2
                        if not _p2 or _p2 in _walked_mat_roots:
                            continue
                        _walked_mat_roots.add(_p2)
                        for _rd, _, _fls in os.walk(_p2):
                            for _sf in _fls:
                                if _sf.lower().endswith('.vtf'):
                                    _sk = os.path.splitext(_sf)[0].lower()
                                    staging_vtf_index.setdefault(_sk, os.path.join(_rd, _sf))

                _TEX_PARAMS_RE = re.compile(
                    r'"\$(?:basetexture|bumpmap|normalmap|detail|envmapmask|'
                    r'lightwarptexture|phongexponenttexture|phongwarptexture|selfillummask|'
                    r'blendmodulatetexture|dudvmap|ambientoccltexture|'
                    r'hdrbasetexture|hdrcompressedtexture)"\s+"([^"$%][^"]*)"',
                    re.IGNORECASE
                )

                for (c, a) in cdmat_by_addon:
                    mat_dir = os.path.join(output, 'materials', 'models', model_namespace, c, a)
                    if not os.path.isdir(mat_dir):
                        continue
                    for vmt_fname in os.listdir(mat_dir):
                        if not vmt_fname.lower().endswith('.vmt'):
                            continue
                        try:
                            with open(os.path.join(mat_dir, vmt_fname),
                                      'r', encoding='utf-8', errors='replace') as _fv:
                                _vmt_content = _fv.read()
                        except OSError:
                            continue
                        for tex_ref in _TEX_PARAMS_RE.findall(_vmt_content):
                            tex_ref = tex_ref.replace('\\', '/').strip()
                            vtf_out = os.path.join(output, 'materials', tex_ref + '.vtf')
                            if os.path.isfile(vtf_out):
                                continue
                            stem_key = tex_ref.rsplit('/', 1)[-1].lower()
                            src_vtf  = staging_vtf_index.get(stem_key)
                            if src_vtf:
                                os.makedirs(os.path.dirname(vtf_out), exist_ok=True)
                                shutil.copy2(src_vtf, vtf_out)
                                self._append_log(f'[CLEAN] → dep: {os.path.relpath(vtf_out, output)} ← {os.path.basename(src_vtf)}')
                            else:
                                self._append_log(f'[CLEAN] WARN: dep not found in staging: {tex_ref}.vtf (ref in {vmt_fname})')

                # ── Step 4: validate MDL material names vs output VMTs ───────
                self._append_log(f'\n[CLEAN] ── Validation ──')
                for (c, a), mat_names in expected_mats_by_addon.items():
                    mat_folder = os.path.join(output, 'materials', 'models', model_namespace, c, a)
                    missing = sorted(
                        mn for mn in mat_names
                        if not os.path.isfile(os.path.join(mat_folder, mn.lower() + '.vmt'))
                    )
                    ok_count = len(mat_names) - len(missing)
                    if missing:
                        self._append_log(f'[CLEAN] WARN {c}/{a}: {ok_count}/{len(mat_names)} VMTs found — {len(missing)} missing:')
                        for mn in missing:
                            sources  = mat_sources_by_addon.get((c, a), {}).get(mn, [])
                            smd_str  = f'  (in: {", ".join(sorted(set(sources)))})' if sources else ''
                            src_dirs = [sd for _, sd in cdmat_by_addon.get((c, a), set())]
                            dir_str  = f'  [searched: {", ".join(src_dirs)}]' if src_dirs else ''
                            self._append_log(f'[CLEAN]   ✗ {mn!r} → expected {mn.lower()}.vmt{smd_str}{dir_str}')
                    else:
                        self._append_log(f'[CLEAN] ✓ {c}/{a}: all {len(mat_names)} VMTs present')

                # Cleanup work dir
                shutil.rmtree(os.path.join(staging_abs, '_clean_work'), ignore_errors=True)
                self._append_log(f'\n[CLEAN] Done. Output: {output}')
                dlg.after(0, lambda: build_btn.config(state='normal'))
                dlg.after(0, lambda: scan_btn.config(state='normal'))

            threading.Thread(target=run, daemon=True).start()

        scan_btn  = self._button(btn_bar, 'Scan', do_scan,
                                 bg=self.BG, fg=self.FG)
        scan_btn.pack(side='left')
        build_btn = self._button(btn_bar, 'Build & Clean', do_build,
                                 bg=self.ACCENT, fg='#ffffff')
        build_btn.pack(side='left', padx=(8, 0))

        def _copy_log():
            content = log_box.get('1.0', 'end-1c')
            dlg.clipboard_clear()
            dlg.clipboard_append(content)

        self._button(btn_bar, 'Copy Log', _copy_log,
                     bg=self.BG, fg=self.FG).pack(side='left', padx=(8, 0))
        self._button(btn_bar, 'Close', dlg.destroy,
                     bg=self.BG, fg=self.FG).pack(side='right')


def main():
    root = tk.Tk()
    app = GMAExtractorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
