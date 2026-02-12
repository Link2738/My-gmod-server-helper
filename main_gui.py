"""
Gemboi's Gmod Server Helper GUI
A clean, modular, user-friendly tool for extracting .gma files, decompiling .mdl files, parsing QC bodygroups, and generating Pointshop Lua files.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import threading
import os
import json
from extractor import extract_gma
from decompiler import decompile_mdl
from qc_parser import parse_qc_bodygroups
from lua_writer import write_pointshop_lua, build_arms_map
from config import load_last_paths, save_last_paths
from steamcmd_downloader import download_workshop_item, download_collection
from corrective_generator import (
    parse_definebones, get_hl2_female_reference,
    generate_corrective,
)

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
        last_type, last_paths, last_output, last_write_bodygroups, last_steamcmd, last_crowbar = load_last_paths()
        self.input_type = tk.StringVar(value=last_type)
        self.input_paths = dict(last_paths)           # per-type path memory
        self.input_path = tk.StringVar(value=self.input_paths.get(last_type, ''))
        self.output_dir = tk.StringVar(value=last_output)
        self.write_bodygroups = tk.BooleanVar(value=last_write_bodygroups)
        self.write_bodygroup_modifications = tk.BooleanVar(value=False)
        self.steamcmd_path = tk.StringVar(value=last_steamcmd)
        self.crowbarcli_path = tk.StringVar(value=last_crowbar)
        self.download_only = tk.BooleanVar(value=False)
        self._switching_type = False                   # guard for trace callbacks

    # ── Helpers ─────────────────────────────────────────────────────────
    def _frame(self, parent, **kw):
        return tk.Frame(parent, bg=self.BG, **kw)

    def _label(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=self.BG, fg=self.FG,
                        font=self.FONT, **kw)

    def _entry(self, parent, textvariable, **kw):
        return tk.Entry(parent, textvariable=textvariable,
                        bg=self.SURFACE, fg=self.FG, insertbackground=self.FG,
                        font=self.FONT, relief='solid', bd=1, **kw)

    def _button(self, parent, text, command, bg=None, fg=None, **kw):
        if bg:
            fg = fg or '#ffffff'
            return tk.Button(parent, text=text, command=command,
                             bg=bg, fg=fg, activebackground=bg,
                             activeforeground=fg, font=self.FONT,
                             relief='raised', bd=1, padx=12, pady=3,
                             cursor='hand2', **kw)
        return ttk.Button(parent, text=text, command=command, **kw)

    def _checkbox(self, parent, text, variable, **kw):
        return ttk.Checkbutton(parent, text=text, variable=variable, **kw)

    # ── Main layout ───────────────────────────────────────────────────
    def setup_widgets(self):
        pad = {'padx': 14, 'pady': 2}
        outer = self._frame(self.root)
        outer.pack(fill='both', expand=True, padx=6, pady=6)

        # ── Header row (title + config) ──────────────────────────────
        hdr = self._frame(outer)
        hdr.pack(fill='x', padx=14, pady=(6, 8))
        tk.Label(hdr, text="Gemboi's Gmod Server Helper",
                 bg=self.BG, fg=self.ACCENT, font=self.FONT_HDR).pack(side='left')
        self._button(hdr, "\u2699  Config", self.open_config_popup).pack(side='right')
        self._button(hdr, "\u26a1 Corrective Fix", self.open_corrective_popup).pack(side='right', padx=(0, 6))

        # ── Input section ────────────────────────────────────────────
        input_frame = self._frame(outer)
        input_frame.pack(fill='x', **pad)

        self._label(input_frame, "Input:").pack(side='left')
        type_combo = ttk.Combobox(input_frame, textvariable=self.input_type,
                                  values=['File', 'Folder', 'Workshop', 'Collection'],
                                  state='readonly', width=10, font=self.FONT)
        type_combo.pack(side='left', padx=(4, 8))

        self._entry(input_frame, self.input_path, width=48).pack(side='left', fill='x', expand=True)
        self._button(input_frame, "Browse", self.browse_input).pack(side='left', padx=(6, 0))

        # ── Output section ───────────────────────────────────────────
        out_frame = self._frame(outer)
        out_frame.pack(fill='x', **pad)

        self._label(out_frame, "Output:").pack(side='left')
        self._entry(out_frame, self.output_dir, width=55).pack(side='left', padx=(4, 0), fill='x', expand=True)
        self._button(out_frame, "Browse", self.browse_output).pack(side='left', padx=(6, 0))

        # ── Per-type path swap on type change ────────────────────────
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
                self.steamcmd_path.get(), self.crowbarcli_path.get())

        self.input_type.trace_add('write', _on_type_change)
        self.input_path.trace_add('write', _on_path_change)
        self.output_dir.trace_add('write', _persist)

        # ── Options ──────────────────────────────────────────────────
        sep = ttk.Separator(outer, orient='horizontal')
        sep.pack(fill='x', padx=14, pady=(6, 2))

        opts = self._frame(outer)
        opts.pack(fill='x', **pad)

        self.write_bodygroups_chk = self._checkbox(
            opts, "Write bodygroup data",
            self.write_bodygroups, command=self.update_modification_checkbox_state)
        self.write_bodygroups_chk.pack(side='left', padx=(0, 16))

        self.write_bodygroup_modifications_chk = self._checkbox(
            opts, "Write bodygroup modifications",
            self.write_bodygroup_modifications)
        self.write_bodygroup_modifications_chk.pack(side='left', padx=(0, 16))

        self.download_only_chk = self._checkbox(
            opts, "Download only (skip .gma extraction)",
            self.download_only)
        self.download_only_chk.pack(side='left')

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
        self.input_type.trace_add('write', update_download_only_state)
        update_download_only_state()

    def update_modification_checkbox_state(self):
        if self.write_bodygroups.get():
            self.write_bodygroup_modifications_chk.config(state='normal')
        else:
            self.write_bodygroup_modifications_chk.config(state='disabled')
            self.write_bodygroup_modifications.set(False)

        # Save config and update in-memory values
        try:
            self.input_paths[self.input_type.get()] = self.input_path.get()
            save_last_paths(
                self.input_type.get(),
                self.input_paths,
                self.output_dir.get(),
                self.write_bodygroups.get(),
                self.steamcmd_path.get(),
                self.crowbarcli_path.get(),
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def open_config_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Configuration")
        popup.geometry("520x180")
        popup.configure(bg=self.BG)
        popup.transient(self.root)
        popup.grab_set()

        # Always reload config from disk for latest values
        config_path = os.path.join('config', 'last_paths.json')
        steamcmd_val = self.steamcmd_path.get()
        crowbar_val = self.crowbarcli_path.get()
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                steamcmd_val = data.get('steamcmd_path', steamcmd_val)
                crowbar_val = data.get('crowbarcli_path', crowbar_val)
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

        body.columnconfigure(1, weight=1)

        def update_config():
            try:
                self.input_paths[self.input_type.get()] = self.input_path.get()
                save_last_paths(
                    self.input_type.get(), self.input_paths,
                    self.output_dir.get(), self.write_bodygroups.get(),
                    steamcmd_entry.get(), crowbar_entry.get())
                self.steamcmd_path.set(steamcmd_entry.get())
                self.crowbarcli_path.set(crowbar_entry.get())
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

        # Save on focus-out
        steamcmd_entry.bind('<FocusOut>', lambda _: update_config())
        crowbar_entry.bind('<FocusOut>', lambda _: update_config())

        # Close button
        self._button(popup, "Done", popup.destroy,
                     bg=self.ACCENT, fg='#ffffff').pack(pady=(0, 10))

    # ── Corrective Fix popup ─────────────────────────────────────────
    def open_corrective_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Proportion Trick Generator")
        popup.geometry("720x580")
        popup.configure(bg=self.BG)
        popup.transient(self.root)
        popup.grab_set()

        body = self._frame(popup)
        body.pack(fill='both', expand=True, padx=14, pady=10)

        tk.Label(body, text="Proportion Trick Generator",
                 bg=self.BG, fg=self.ACCENT, font=self.FONT_HDR).pack(anchor='w', pady=(0, 4))
        tk.Label(body,
                 text="Generates proportion trick SMDs directly from $definebone\n"
                      "data (pure math, no Blender required).",
                 bg=self.BG, fg=self.FG, font=self.FONT,
                 justify='left').pack(anchor='w', pady=(0, 8))

        # ── QC Input ─────────────────────────────────────────────────
        qc_frame = self._frame(body)
        qc_frame.pack(fill='x', pady=2)
        self._label(qc_frame, "Model QC:").pack(side='left')
        qc_var = tk.StringVar()
        self._entry(qc_frame, qc_var, width=50).pack(side='left', fill='x', expand=True, padx=(6, 4))

        def browse_qc():
            path = filedialog.askopenfilename(
                title="Select decompiled .qc file",
                filetypes=[("QC File", "*.qc"), ("All files", "*.*")])
            if path:
                qc_var.set(path)

        self._button(qc_frame, "Browse", browse_qc).pack(side='left')

        # ── Reference source ─────────────────────────────────────────
        ref_frame = self._frame(body)
        ref_frame.pack(fill='x', pady=2)
        self._label(ref_frame, "Reference:").pack(side='left')

        ref_type = tk.StringVar(value='builtin')
        ttk.Radiobutton(ref_frame, text="HL2 Female (built-in)",
                        variable=ref_type, value='builtin').pack(side='left', padx=(6, 12))
        ttk.Radiobutton(ref_frame, text="Custom QC",
                        variable=ref_type, value='custom').pack(side='left')

        custom_ref_frame = self._frame(body)
        custom_ref_frame.pack(fill='x', pady=2)
        self._label(custom_ref_frame, " ").pack(side='left')
        custom_ref_var = tk.StringVar()
        custom_ref_entry = self._entry(custom_ref_frame, custom_ref_var, width=46)
        custom_ref_entry.pack(side='left', fill='x', expand=True, padx=(6, 4))

        def browse_custom_ref():
            path = filedialog.askopenfilename(
                title="Select reference .qc file",
                filetypes=[("QC File", "*.qc"), ("All files", "*.*")])
            if path:
                custom_ref_var.set(path)

        custom_ref_btn = self._button(custom_ref_frame, "Browse", browse_custom_ref)
        custom_ref_btn.pack(side='left')

        def _toggle_custom(*_):
            state = 'normal' if ref_type.get() == 'custom' else 'disabled'
            custom_ref_entry.config(state=state)
            if isinstance(custom_ref_btn, ttk.Button):
                custom_ref_btn.config(state=state)
            else:
                custom_ref_btn.config(state=state)

        ref_type.trace_add('write', _toggle_custom)
        _toggle_custom()

        # ── Output directory ─────────────────────────────────────────
        out_frame = self._frame(body)
        out_frame.pack(fill='x', pady=2)
        self._label(out_frame, "Output:").pack(side='left')
        corr_out_var = tk.StringVar(value=self.output_dir.get())
        self._entry(out_frame, corr_out_var, width=50).pack(side='left', fill='x', expand=True, padx=(6, 4))

        def browse_corr_out():
            path = filedialog.askdirectory(title="Select output directory")
            if path:
                corr_out_var.set(path)

        self._button(out_frame, "Browse", browse_corr_out).pack(side='left')

        # ── Options ──────────────────────────────────────────────────
        sep = ttk.Separator(body, orient='horizontal')
        sep.pack(fill='x', pady=(8, 4))

        opts_frame = self._frame(body)
        opts_frame.pack(fill='x', pady=2)

        # Anims subfolder
        self._label(opts_frame, "Anims folder:").pack(side='left')
        anims_folder_var = tk.StringVar(value='anims')
        self._entry(opts_frame, anims_folder_var, width=18).pack(side='left', padx=(6, 16))

        # ── Log area ─────────────────────────────────────────────────
        sep2 = ttk.Separator(body, orient='horizontal')
        sep2.pack(fill='x', pady=(8, 4))

        corr_log = scrolledtext.ScrolledText(
            body, height=12, bg='#1e1e1e', fg='#cccccc',
            insertbackground='#cccccc', font=('Consolas', 9),
            relief='solid', bd=1, wrap='word')
        corr_log.pack(fill='both', expand=True, pady=(0, 6))

        # ── Buttons ──────────────────────────────────────────────────
        btn_bar = self._frame(body)
        btn_bar.pack(fill='x', pady=(0, 4))

        def do_generate():
            qc_path = qc_var.get().strip()
            out_dir = corr_out_var.get().strip()

            if not qc_path or not os.path.isfile(qc_path):
                messagebox.showwarning("Missing QC", "Please select a valid .qc file.", parent=popup)
                return
            if not out_dir:
                messagebox.showwarning("Missing output", "Please select an output directory.", parent=popup)
                return

            corr_log.delete('1.0', tk.END)

            def log_msg(msg):
                corr_log.insert('end', msg + '\n')
                corr_log.see('end')
                corr_log.update_idletasks()

            # Reference bones
            if ref_type.get() == 'custom':
                ref_path = custom_ref_var.get().strip()
                if not ref_path or not os.path.isfile(ref_path):
                    messagebox.showwarning("Missing reference",
                                           "Please select a valid reference .qc file.", parent=popup)
                    return
                log_msg(f'[INFO] Loading custom reference: {ref_path}')
                ref_bones = parse_definebones(ref_path)
                if not ref_bones:
                    log_msg('[ERROR] No $definebone lines found in custom reference.')
                    return
                log_msg(f'[INFO] Custom reference: {len(ref_bones)} bones')
            else:
                ref_bones = get_hl2_female_reference()
                log_msg(f'[INFO] Using built-in HL2 female reference ({len(ref_bones)} bones)')

            def _run():
                result = generate_corrective(
                    qc_path, out_dir,
                    log_callback=log_msg,
                    ref_bones=ref_bones,
                    anims_subfolder=anims_folder_var.get().strip() or 'anims',
                )

                if result:
                    matched, total, out = result
                    log_msg(f'\n[DONE] {matched}/{total} bones matched.')
                    log_msg(f'[DONE] Output: {out}')
                    log_msg(f'[DONE] QC snippet: {os.path.join(out, "corrective_qc_snippet.txt")}')
                    log_msg(f'[INFO] Paste the QC snippet AFTER $sequence "reference" and recompile.')
                else:
                    log_msg('[ERROR] Failed to generate corrective animation.')

            threading.Thread(target=_run, daemon=True).start()

        gen_btn = self._button(btn_bar, "Generate", do_generate,
                               bg=self.GREEN, fg='#ffffff')
        gen_btn.pack(side='right')
        self._button(btn_bar, "Close", popup.destroy).pack(side='left')

    def browse_input(self):
        t = self.input_type.get()
        if t == 'File':
            path = filedialog.askopenfilename(
                title="Select .gma, .bin, or .mdl file",
                filetypes=[
                    ("Supported files", "*.gma *.bin *.mdl"),
                    ("Garry's Mod Addon", "*.gma *.bin"),
                    ("Source Model", "*.mdl"),
                ])
        elif t == 'Folder':
            path = filedialog.askdirectory(title="Select folder with models, .gma, or .bin files")
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

    def show_model_type_selector(self, mdl_files):
        """Show a dialog to let user select item type for each model"""
        if not mdl_files:
            return {}

        dialog = tk.Toplevel(self.root)
        dialog.title("Select Item Types")
        dialog.geometry("720x520")
        dialog.configure(bg=self.BG)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Select the type for each model:",
                 bg=self.BG, fg=self.FG, font=self.FONT_BOLD).pack(pady=(12, 6))

        # ── Scrollable frame ─────────────────────────────────────────
        container = self._frame(dialog)
        container.pack(fill='both', expand=True, padx=14)

        canvas = tk.Canvas(container, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        scrollable_frame = self._frame(canvas)

        scrollable_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        dialog.bind('<Destroy>', lambda _: canvas.unbind_all('<MouseWheel>'))

        # Store selections
        selections = {}

        for mdl_path in mdl_files:
            row = self._frame(scrollable_frame)
            row.pack(fill='x', padx=8, pady=3)

            model_name = os.path.basename(mdl_path)
            self._label(row, model_name, width=40, anchor='w').pack(side='left', padx=(0, 8))

            type_var = tk.StringVar(value='victim_playermodel')
            selections[mdl_path] = type_var

            for label_text, value in [("Victim Model", "victim_playermodel"),
                                      ("Bear Model", "bear_playermodel"),
                                      ("Accessory", "accessory")]:
                ttk.Radiobutton(row, text=label_text, variable=type_var,
                                value=value).pack(side='left', padx=6)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # ── Buttons ──────────────────────────────────────────────────
        btn_bar = self._frame(dialog)
        btn_bar.pack(pady=10)

        result = {'confirmed': False, 'selections': {}}

        def on_confirm():
            result['confirmed'] = True
            result['selections'] = {path: var.get() for path, var in selections.items()}
            dialog.destroy()

        def on_cancel():
            result['confirmed'] = False
            dialog.destroy()

        self._button(btn_bar, "Confirm", on_confirm,
                     bg=self.GREEN, fg='#ffffff').pack(side='left', padx=6)
        self._button(btn_bar, "Cancel", on_cancel,
                     bg=self.RED, fg='#ffffff').pack(side='left', padx=6)

        self.root.wait_window(dialog)
        return result

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
        write_bodygroup_modifications = self.write_bodygroup_modifications.get()
        download_only = self.download_only.get()

        def log_callback(msg):
            self.log_widget.insert('end', msg + '\n')
            self.log_widget.see('end')

        try:
            if input_type == 'File':
                if input_path.lower().endswith('.mdl'):
                    # Single .mdl file — skip extraction, process directly
                    log_callback(f'[INFO] Direct .mdl input: {input_path}')
                    # Gather sibling .mdl files in the same folder for arms detection
                    parent_dir = os.path.dirname(input_path)
                    sibling_mdls = self.find_mdl_files(parent_dir)
                    if not self._process_mdl_list(
                            [input_path], output_dir, crowbarcli_path,
                            write_bodygroups, write_bodygroup_modifications,
                            log_callback, extra_mdls_for_arms=sibling_mdls):
                        self.process_button.config(state='normal')
                        return
                else:
                    # Single .gma or .bin file (GMA format)
                    extract_dir = os.path.join(output_dir, 'extracted')
                    os.makedirs(extract_dir, exist_ok=True)
                    extract_gma(input_path, extract_dir, log_callback)
                    gma_name = os.path.splitext(os.path.basename(input_path))[0]
                    gma_folder = os.path.join(extract_dir, gma_name)
                    if not os.path.isdir(gma_folder):
                        log_callback(f'[WARN] Expected folder {gma_folder} not found after extraction.')
                        return
                    mdl_files = self.find_mdl_files(gma_folder)
                    if not mdl_files:
                        log_callback('[WARN] No .mdl files found in extracted folder.')
                    else:
                        if not self._process_mdl_list(mdl_files, output_dir, crowbarcli_path,
                                                      write_bodygroups, write_bodygroup_modifications, log_callback):
                            self.process_button.config(state='normal')
                            return
            elif input_type == 'Folder':
                # Folder may contain .gma files (needs extraction) and/or
                # already-extracted model content (.mdl files directly).
                gma_files = []
                loose_mdl_files = []
                for root, dirs, files in os.walk(input_path):
                    for f in files:
                        fl = f.lower()
                        if fl.endswith(('.gma', '.bin')):
                            gma_files.append(os.path.join(root, f))
                        elif fl.endswith('.mdl'):
                            loose_mdl_files.append(os.path.join(root, f))

                all_mdl_files = list(loose_mdl_files)

                if gma_files:
                    log_callback(f'[INFO] Found {len(gma_files)} .gma/.bin file(s) — extracting...')
                    for gma_path in gma_files:
                        gma_file = os.path.basename(gma_path)
                        extract_dir = os.path.join(output_dir, 'extracted', os.path.splitext(gma_file)[0])
                        os.makedirs(extract_dir, exist_ok=True)
                        extract_gma(gma_path, extract_dir, log_callback)
                        all_mdl_files.extend(self.find_mdl_files(extract_dir))

                if loose_mdl_files:
                    log_callback(f'[INFO] Found {len(loose_mdl_files)} loose .mdl file(s) in folder.')

                if not all_mdl_files:
                    log_callback('[WARN] No .gma, .bin, or .mdl files found in folder.')
                else:
                    if not self._process_mdl_list(all_mdl_files, output_dir, crowbarcli_path,
                                                  write_bodygroups, write_bodygroup_modifications, log_callback):
                        self.process_button.config(state='normal')
                        return
            elif input_type == 'Workshop' or input_type == 'Collection':
                # Before any SteamCMD download, clean the steamapps workshop content folder to avoid contamination
                steamcmd_dir = os.path.dirname(steamcmd_path)
                steamapps_content_dir = os.path.join(steamcmd_dir, 'steamapps', 'workshop', 'content', '4000')
                try:
                    if os.path.isdir(steamapps_content_dir):
                        import shutil
                        shutil.rmtree(steamapps_content_dir)
                        log_callback(f'[INFO] Deleted old workshop content folder: {steamapps_content_dir}')
                except Exception as e:
                    log_callback(f'[WARN] Could not delete workshop content folder: {e}')

                if input_type == 'Workshop':
                    # Download a single workshop item using SteamCMD
                    gma_file = download_workshop_item(steamcmd_path, input_path, output_dir, log_callback)
                    if self.download_only.get():
                        if gma_file:
                            log_callback('[INFO] Workshop download complete (download only mode).')
                        else:
                            log_callback('[ERROR] Failed to download workshop item.')
                        return
                    if gma_file:
                        extract_dir = os.path.join(output_dir, 'extracted', os.path.splitext(os.path.basename(gma_file))[0])
                        os.makedirs(extract_dir, exist_ok=True)
                        extract_gma(gma_file, extract_dir, log_callback)
                        mdl_files = self.find_mdl_files(extract_dir)
                        
                        # Show model type selector
                        if mdl_files:
                            if not self._process_mdl_list(mdl_files, output_dir, crowbarcli_path,
                                                          write_bodygroups, write_bodygroup_modifications, log_callback):
                                self.process_button.config(state='normal')
                                return
                    else:
                        log_callback('[ERROR] Failed to download or extract workshop item.')
                elif input_type == 'Collection':
                    # Download all items in a collection using SteamCMD, then extract/process after all downloads are complete
                    gma_files = download_collection(steamcmd_path, input_path, output_dir, log_callback)
                    if self.download_only.get():
                        if gma_files:
                            log_callback('[INFO] Collection download complete (download only mode).')
                        else:
                            log_callback('[ERROR] Failed to download any items from collection.')
                        return
                    if gma_files:
                        log_callback(f'[INFO] All collection downloads complete. Beginning extraction and processing...')
                        
                        # Collect all mdl files first
                        all_mdl_files = []
                        for gma_file in gma_files:
                            extract_dir = os.path.join(output_dir, 'extracted', os.path.splitext(os.path.basename(gma_file))[0])
                            os.makedirs(extract_dir, exist_ok=True)
                            extract_gma(gma_file, extract_dir, log_callback)
                            mdl_files = self.find_mdl_files(extract_dir)
                            all_mdl_files.extend(mdl_files)
                        
                        # Show model type selector for all models
                        if all_mdl_files:
                            if not self._process_mdl_list(all_mdl_files, output_dir, crowbarcli_path,
                                                          write_bodygroups, write_bodygroup_modifications, log_callback):
                                self.process_button.config(state='normal')
                                return
                    else:
                        log_callback('[ERROR] Failed to download or extract any items from collection.')
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
                          write_bodygroups, write_bodygroup_modifications,
                          log_callback, extra_mdls_for_arms=None):
        """
        Common processing pipeline for a list of MDL files:
        1. Build arms model lookup
        2. Filter _arms from the type selector
        3. Decompile, parse QC, write Lua for each selected model

        extra_mdls_for_arms: additional .mdl paths to consider when
        building the arms map (e.g. sibling files when processing a
        single .mdl).

        Returns False if the user cancelled, True otherwise.
        """
        if not mdl_files:
            log_callback('[WARN] No .mdl files found.')
            return True

        # Build mapping of base model -> arms model path
        # Include extra sibling mdls so arms detection works for single-file input
        arms_pool = list(mdl_files)
        if extra_mdls_for_arms:
            seen = set(os.path.normpath(p) for p in arms_pool)
            for p in extra_mdls_for_arms:
                if os.path.normpath(p) not in seen:
                    arms_pool.append(p)
        arms_map = build_arms_map(arms_pool)
        for base, arms in arms_map.items():
            log_callback(f'[INFO] Found arms model: {os.path.basename(arms)} -> {os.path.basename(base)}')

        # Filter out arms models from the selector (users don't need to tag them)
        # Catches both _arms in the name and bare 'arms.mdl' files
        def _is_arms_model(path):
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            return '_arms' in stem or stem == 'arms'

        selectable = [p for p in mdl_files if not _is_arms_model(p)]
        if not selectable:
            log_callback('[WARN] All models are arms models; nothing to generate.')
            return True

        selection_result = self.show_model_type_selector(selectable)
        if not selection_result['confirmed']:
            log_callback('[INFO] Processing cancelled by user.')
            return False

        model_types = selection_result['selections']
        for mdl_path in selectable:
            item_type = model_types.get(mdl_path, 'victim_playermodel')
            crowbar_outdir = os.path.join(
                output_dir, 'crowbar_out',
                os.path.splitext(os.path.basename(mdl_path))[0]
            )
            log_callback(f'[INFO] Decompiling: {mdl_path}')
            decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback)
            qc_path = self.find_qc_file(crowbar_outdir)
            if qc_path:
                bodygroups = parse_qc_bodygroups(qc_path) if write_bodygroups else []
                write_pointshop_lua(
                    mdl_path, bodygroups, output_dir, log_callback,
                    write_bodygroup_modifications, item_type,
                    arms_model=arms_map.get(mdl_path)
                )
        return True


def main():
    root = tk.Tk()
    app = GMAExtractorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
