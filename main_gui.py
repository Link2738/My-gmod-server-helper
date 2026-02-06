"""
Gemboi's Gmod Server Helper GUI
A clean, modular, user-friendly tool for extracting .gma files, decompiling .mdl files, parsing QC bodygroups, and generating Pointshop Lua files.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import threading
import os
import json
from extractor import extract_gma
from decompiler import decompile_mdl
from qc_parser import parse_qc_bodygroups
from lua_writer import write_pointshop_lua
from config import load_last_paths, save_last_paths
from steamcmd_downloader import download_workshop_item, download_collection

class GMAExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemboi's Gmod Server Helper GUI")
        self.setup_vars()
        self.setup_widgets()
        self.abort_flag = {'abort': False}

    def setup_vars(self):
        last_type, last_path, last_output, last_write_bodygroups, last_steamcmd, last_crowbar = load_last_paths()
        self.input_type = tk.StringVar(value=last_type)
        self.input_path = tk.StringVar(value=last_path)
        self.output_dir = tk.StringVar(value=last_output)
        self.write_bodygroups = tk.BooleanVar(value=last_write_bodygroups)
        self.write_bodygroup_modifications = tk.BooleanVar(value=False)
        self.steamcmd_path = tk.StringVar(value=last_steamcmd)
        self.crowbarcli_path = tk.StringVar(value=last_crowbar)
        self.download_only = tk.BooleanVar(value=False)
        # self.skip_bsp = tk.BooleanVar(value=False)

    def setup_widgets(self):
        row = tk.Frame(self.root)
        row.pack(anchor='w', pady=2)
        tk.Label(row, text="Input type:").pack(side='left')
        type_menu = tk.OptionMenu(row, self.input_type, 'File', 'Folder', 'Workshop', 'Collection')
        type_menu.pack(side='left')
        self.input_entry = tk.Entry(row, textvariable=self.input_path, width=50)
        self.input_entry.pack(side='left', padx=4)
        self.browse_btn = tk.Button(row, text="Browse", command=self.browse_input)
        self.browse_btn.pack(side='left')

        # Save input type and input path on change
        def save_input_config(*args):
            save_last_paths(
                self.input_type.get(),
                self.input_path.get(),
                self.output_dir.get(),
                self.write_bodygroups.get(),
                self.steamcmd_path.get(),
                self.crowbarcli_path.get()
            )
        self.input_type.trace_add('write', save_input_config)
        self.input_path.trace_add('write', save_input_config)

        # Config button
        config_btn = tk.Button(self.root, text="Config", command=self.open_config_popup)
        config_btn.pack(anchor='ne', padx=4, pady=2)

        tk.Label(self.root, text="Output Directory:").pack(anchor='w')
        output_entry = tk.Entry(self.root, textvariable=self.output_dir, width=70)
        output_entry.pack(anchor='w')
        tk.Button(self.root, text="Browse", command=self.browse_output).pack(anchor='w')

        # Save output dir on change
        def save_output_config(*args):
            save_last_paths(
                self.input_type.get(),
                self.input_path.get(),
                self.output_dir.get(),
                self.write_bodygroups.get(),
                self.steamcmd_path.get(),
                self.crowbarcli_path.get()
            )
        self.output_dir.trace_add('write', save_output_config)

        # Write bodygroup data checkbox
        self.write_bodygroups_chk = tk.Checkbutton(self.root, text="Write bodygroup data to Lua", variable=self.write_bodygroups, command=self.update_modification_checkbox_state)
        self.write_bodygroups_chk.pack(anchor='w')

        # Write bodygroup modification logic checkbox
        self.write_bodygroup_modifications_chk = tk.Checkbutton(self.root, text="Write bodygroup modification logic to Lua", variable=self.write_bodygroup_modifications)
        self.write_bodygroup_modifications_chk.pack(anchor='w')

        # Workshop Download Only checkbox
        self.download_only_chk = tk.Checkbutton(self.root, text="Workshop Download Only (do not read .gma files)", variable=self.download_only)
        self.download_only_chk.pack(anchor='w')

        # Console output
        self.log_widget = scrolledtext.ScrolledText(self.root, height=12, width=90)
        self.log_widget.pack(fill='both', expand=True)

        # Copy output button
        self.copy_button = tk.Button(self.root, text="Copy Console Output", command=self.copy_console_output)
        self.copy_button.pack(pady=2)

        # Extract & Generate Lua button
        self.process_button = tk.Button(self.root, text="Extract && Generate Lua", command=self.start_process)
        self.process_button.pack(pady=10)

        # Abort button
        self.abort_button = tk.Button(self.root, text="Abort", command=self.abort_process, fg='red')
        self.abort_button.pack(pady=2)

        # Only update state, do not recreate widgets
        def update_download_only_state(*args):
            input_type = self.input_type.get()
            if input_type in ('Workshop', 'Collection'):
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
            save_last_paths(
                self.input_type.get(),
                self.input_path.get(),
                self.output_dir.get(),
                self.write_bodygroups.get(),
                self.steamcmd_path.get(),
                self.crowbarcli_path.get()
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def open_config_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Configuration")
        popup.geometry("400x180")

        # Always reload config from disk for latest values
        import json, os
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

        tk.Label(popup, text="SteamCMD path:").pack(anchor='w', padx=10, pady=(10,0))
        steamcmd_entry = tk.Entry(popup, width=50)
        steamcmd_entry.pack(anchor='w', padx=10)
        steamcmd_entry.insert(0, steamcmd_val)

        tk.Label(popup, text="CrowbarCLI path:").pack(anchor='w', padx=10, pady=(10,0))
        crowbar_entry = tk.Entry(popup, width=50)
        crowbar_entry.pack(anchor='w', padx=10)
        crowbar_entry.insert(0, crowbar_val)

        def update_config():
            # Save config and update in-memory values
            try:
                save_last_paths(
                    self.input_type.get(),
                    self.input_path.get(),
                    self.output_dir.get(),
                    self.write_bodygroups.get(),
                    steamcmd_entry.get(),
                    crowbar_entry.get()
                )
                self.steamcmd_path.set(steamcmd_entry.get())
                self.crowbarcli_path.set(crowbar_entry.get())
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

        def browse_steamcmd():
            path = filedialog.askopenfilename(title="Select steamcmd executable", filetypes=[("SteamCMD Executable", "steamcmd.exe")])
            if path:
                steamcmd_entry.delete(0, tk.END)
                steamcmd_entry.insert(0, path)
                update_config()

        def browse_crowbar():
            path = filedialog.askopenfilename(
                title="Select crowbarcli executable",
                filetypes=[
                    ("CrowbarCommandLineDecomp", "CrowbarCommandLineDecomp.exe"),
                    ("CrowbarCLI Executable", "crowbarcli.exe"),
                ]
            )
            if path:
                crowbar_entry.delete(0, tk.END)
                crowbar_entry.insert(0, path)
                update_config()

        # Bind entry changes to update config live
        def on_steamcmd_change(event):
            update_config()

        def on_crowbar_change(event):
            update_config()

        steamcmd_entry.bind('<FocusOut>', on_steamcmd_change)
        crowbar_entry.bind('<FocusOut>', on_crowbar_change)

        browse_steamcmd_btn = tk.Button(popup, text="Browse", command=browse_steamcmd)
        browse_steamcmd_btn.pack(anchor='w', padx=10, pady=(0,5))
        browse_crowbar_btn = tk.Button(popup, text="Browse", command=browse_crowbar)
        browse_crowbar_btn.pack(anchor='w', padx=10, pady=(0,10))

    def browse_input(self):
        t = self.input_type.get()
        if t == 'File':
            path = filedialog.askopenfilename(title="Select .gma file", filetypes=[("Garry's Mod Addon", "*.gma")])
        elif t == 'Folder':
            path = filedialog.askdirectory(title="Select folder containing .gma files")
        else:
            path = ''
        if path:
            self.input_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.output_dir.set(path)

    def browse_steamcmd(self):
        path = filedialog.askopenfilename(title="Select steamcmd executable", filetypes=[("SteamCMD Executable", "steamcmd.exe")])
        if path:
            self.steamcmd_path.set(path)

    def abort_process(self):
        self.abort_flag['abort'] = True
        self.log_widget.insert('end', '[INFO] Abort requested. Waiting for current operation to finish...\n')
        self.log_widget.see('end')

    def copy_console_output(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_widget.get('1.0', tk.END))
        self.root.update()
        messagebox.showinfo("Copied!", "Console output copied to clipboard.")

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
        # skip_bsp removed

        def log_callback(msg):
            self.log_widget.insert('end', msg + '\n')
            self.log_widget.see('end')

        try:
            if input_type == 'File':
                # Single .gma file
                extract_dir = os.path.join(output_dir, 'extracted')
                os.makedirs(extract_dir, exist_ok=True)
                extract_gma(input_path, extract_dir, log_callback)
                # Find folder matching gma file name
                gma_name = os.path.splitext(os.path.basename(input_path))[0]
                gma_folder = os.path.join(extract_dir, gma_name)
                if not os.path.isdir(gma_folder):
                    log_callback(f'[WARN] Expected folder {gma_folder} not found after extraction.')
                    return
                # Recursively find .mdl files in gma_folder
                mdl_files = []
                for root, dirs, files in os.walk(gma_folder):
                    for f in files:
                        if f.lower().endswith('.mdl'):
                            mdl_files.append(os.path.join(root, f))
                if not mdl_files:
                    log_callback('[WARN] No .mdl files found in extracted folder.')
                else:
                    for mdl_path in mdl_files:
                        crowbar_outdir = os.path.join(output_dir, 'crowbar_out', os.path.splitext(os.path.basename(mdl_path))[0])
                        log_callback(f'[INFO] Decompiling: {mdl_path}')
                        decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback)
                        qc_path = self.find_qc_file(crowbar_outdir)
                        if qc_path:
                            bodygroups = parse_qc_bodygroups(qc_path)
                            print("write_bodygroup_modifications:", write_bodygroup_modifications)
                            if write_bodygroups:
                                write_pointshop_lua(mdl_path, bodygroups, output_dir, log_callback, write_bodygroup_modifications)
                            else:
                                write_pointshop_lua(mdl_path, [], output_dir, log_callback, False)
            elif input_type == 'Folder':
                # Recursively search for .gma files in folder and subfolders
                gma_files = []
                for root, dirs, files in os.walk(input_path):
                    for f in files:
                        if f.lower().endswith('.gma'):
                            gma_files.append(os.path.join(root, f))
                for gma_path in gma_files:
                    gma_file = os.path.basename(gma_path)
                    extract_dir = os.path.join(output_dir, 'extracted', os.path.splitext(gma_file)[0])
                    os.makedirs(extract_dir, exist_ok=True)
                    extract_gma(gma_path, extract_dir, log_callback)
                    mdl_files = self.find_mdl_files(extract_dir)
                    for mdl_path in mdl_files:
                        crowbar_outdir = os.path.join(output_dir, 'crowbar_out', os.path.splitext(os.path.basename(mdl_path))[0])
                        decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback)
                        qc_path = self.find_qc_file(crowbar_outdir)
                        if qc_path:
                            bodygroups = parse_qc_bodygroups(qc_path)
                            if self.write_bodygroups.get():
                                write_pointshop_lua(mdl_path, bodygroups, output_dir, log_callback, write_bodygroup_modifications)
                            else:
                                write_pointshop_lua(mdl_path, [], output_dir, log_callback, False)
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
                        for mdl_path in mdl_files:
                            crowbar_outdir = os.path.join(output_dir, 'crowbar_out', os.path.splitext(os.path.basename(mdl_path))[0])
                            decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback)
                            qc_path = self.find_qc_file(crowbar_outdir)
                            if qc_path:
                                bodygroups = parse_qc_bodygroups(qc_path)
                                if self.write_bodygroups.get():
                                    write_pointshop_lua(mdl_path, bodygroups, output_dir, log_callback, write_bodygroup_modifications)
                                else:
                                    write_pointshop_lua(mdl_path, [], output_dir, log_callback, False)
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
                        for gma_file in gma_files:
                            extract_dir = os.path.join(output_dir, 'extracted', os.path.splitext(os.path.basename(gma_file))[0])
                            os.makedirs(extract_dir, exist_ok=True)
                            extract_gma(gma_file, extract_dir, log_callback)
                            mdl_files = self.find_mdl_files(extract_dir)
                            for mdl_path in mdl_files:
                                crowbar_outdir = os.path.join(output_dir, 'crowbar_out', os.path.splitext(os.path.basename(mdl_path))[0])
                                decompile_mdl(mdl_path, crowbarcli_path, crowbar_outdir, log_callback)
                                qc_path = self.find_qc_file(crowbar_outdir)
                                if qc_path:
                                    bodygroups = parse_qc_bodygroups(qc_path)
                                    if self.write_bodygroups.get():
                                        write_pointshop_lua(mdl_path, bodygroups, output_dir, log_callback, write_bodygroup_modifications)
                                    else:
                                        write_pointshop_lua(mdl_path, [], output_dir, log_callback, False)
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


def main():
    root = tk.Tk()
    app = GMAExtractorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
