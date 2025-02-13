# ui.py
# -*- coding: utf-8 -*-

import logging
import os
import re
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
import traceback

from config_manager import load_config, save_config, test_llm_config, test_embedding_config
from utils import read_file, save_string_to_txt, clear_file_content

from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    get_last_n_chapters_text,
    enrich_chapter_text
)
from consistency_checker import check_consistency

# ---- Import the tooltip texts ----
from tooltips import tooltips


# ----------------- 右键菜单功能封装 -----------------
class TextWidgetContextMenu:
    """
    为 customtkinter.TextBox 或 tkinter.Text 提供右键复制/剪切/粘贴/全选的功能。
    """
    def __init__(self, widget):
        self.widget = widget
        self.menu = tk.Menu(widget, tearoff=0)
        self.menu.add_command(label="复制", command=self.copy)
        self.menu.add_command(label="粘贴", command=self.paste)
        self.menu.add_command(label="剪切", command=self.cut)
        self.menu.add_separator()
        self.menu.add_command(label="全选", command=self.select_all)
        
        # 绑定右键事件
        self.widget.bind("<Button-3>", self.show_menu)
        
    def show_menu(self, event):
        if isinstance(self.widget, ctk.CTkTextbox):
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()
            
    def copy(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except tk.TclError:
            pass  # 没有选中文本时忽略错误

    def paste(self):
        try:
            text = self.widget.clipboard_get()
            self.widget.insert("insert", text)
        except tk.TclError:
            pass  # 剪贴板为空时忽略错误

    def cut(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.delete("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except tk.TclError:
            pass  # 没有选中文本时忽略错误

    def select_all(self):
        self.widget.tag_add("sel", "1.0", "end")


def log_error(message: str):
    logging.error(f"{message}\n{traceback.format_exc()}")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class NovelGeneratorGUI:
    """
    小说生成器的主GUI类，包含所有的界面布局、事件处理、与后端逻辑的交互等。
    """
    def __init__(self, master):
        self.master = master
        self.master.title("Novel Generator GUI")

        # 设置窗口图标
        try:
            if os.path.exists("icon.ico"):
                self.master.iconbitmap("icon.ico")
        except Exception:
            pass

        self.master.geometry("1350x840")

        # --------------- 配置文件路径 ---------------
        self.config_file = "config.json"
        self.loaded_config = load_config(self.config_file)

        # --------------- 主要属性变量 ---------------
        # -- LLM通用参数 --
        self.api_key_var = ctk.StringVar(value=self.loaded_config.get("api_key", ""))
        self.base_url_var = ctk.StringVar(value=self.loaded_config.get("base_url", "https://api.openai.com/v1"))
        self.interface_format_var = ctk.StringVar(value=self.loaded_config.get("interface_format", "OpenAI"))
        self.model_name_var = ctk.StringVar(value=self.loaded_config.get("model_name", "gpt-4o-mini"))
        self.temperature_var = ctk.DoubleVar(value=self.loaded_config.get("temperature", 0.7))
        self.max_tokens_var = ctk.IntVar(value=self.loaded_config.get("max_tokens", 8192))
        self.timeout_var = ctk.IntVar(value=self.loaded_config.get("timeout", 600))

        # -- Embedding相关 --
        self.embedding_interface_format_var = ctk.StringVar(value=self.loaded_config.get("embedding_interface_format", "OpenAI"))
        self.embedding_api_key_var = ctk.StringVar(value=self.loaded_config.get("embedding_api_key", ""))
        self.embedding_url_var = ctk.StringVar(value=self.loaded_config.get("embedding_url", "https://api.openai.com/v1"))
        self.embedding_model_name_var = ctk.StringVar(value=self.loaded_config.get("embedding_model_name", "text-embedding-ada-002"))
        self.embedding_retrieval_k_var = ctk.StringVar(value=str(self.loaded_config.get("embedding_retrieval_k", 4)))

        # -- 小说参数相关 --
        self.topic_default = self.loaded_config.get("topic", "")
        self.genre_var = ctk.StringVar(value=self.loaded_config.get("genre", "玄幻"))
        self.num_chapters_var = ctk.StringVar(value=str(self.loaded_config.get("num_chapters", 10)))
        self.word_number_var = ctk.StringVar(value=str(self.loaded_config.get("word_number", 3000)))
        self.filepath_var = ctk.StringVar(value=self.loaded_config.get("filepath", ""))

        # -- 章节参数及可选要素 --
        self.chapter_num_var = ctk.StringVar(value=str(self.loaded_config.get("chapter_num", "1")))
        self.characters_involved_var = ctk.StringVar(value=self.loaded_config.get("characters_involved", ""))
        self.key_items_var = ctk.StringVar(value=self.loaded_config.get("key_items", ""))
        self.scene_location_var = ctk.StringVar(value=self.loaded_config.get("scene_location", ""))
        self.time_constraint_var = ctk.StringVar(value=self.loaded_config.get("time_constraint", ""))
        
        self.chapter_lang_format_var = ctk.StringVar(value=self.loaded_config.get("chapter_lang_format", ""))

        # 用于存储本章指导（多行）
        self.user_guidance_default = self.loaded_config.get("user_guidance", "")

        # --------------- 整体Tab布局 ---------------
        self.tabview = ctk.CTkTabview(self.master)
        self.tabview.pack(fill="both", expand=True)

        # 创建各个标签页
        self.main_tab = self.tabview.add("Main Functions")
        self.setting_tab = self.tabview.add("Novel Architecture")
        self.directory_tab = self.tabview.add("Chapter Blueprint")
        self.character_tab = self.tabview.add("Character State")
        self.summary_tab = self.tabview.add("Global Summary")
        self.chapters_view_tab = self.tabview.add("Chapters Manage")

        # 构建各个Tab的UI
        self.build_main_tab()
        self.build_setting_tab()
        self.build_directory_tab()
        self.build_character_tab()
        self.build_summary_tab()
        self.build_chapters_tab()

    # ----------------- 通用辅助函数 -----------------
    def show_tooltip(self, key: str):
        """显示自定义的tooltip文本。"""
        info_text = tooltips.get(key, "暂无说明")
        messagebox.showinfo("参数说明", info_text)

    def safe_get_int(self, var, default=1):
        """从CTk的StringVar中安全地读取整数，若失败则返回default并重置变量值。"""
        try:
            val_str = str(var.get()).strip()
            return int(val_str)
        except:
            var.set(str(default))
            return default

    def log(self, message: str):
        """在左侧日志框输出信息。"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def safe_log(self, message: str):
        """线程安全地在日志框输出信息。"""
        self.master.after(0, lambda: self.log(message))

    def disable_button_safe(self, btn):
        """线程安全地禁用按钮。"""
        self.master.after(0, lambda: btn.configure(state="disabled"))

    def enable_button_safe(self, btn):
        """线程安全地启用按钮。"""
        self.master.after(0, lambda: btn.configure(state="normal"))

    def handle_exception(self, context: str):
        """在出现异常时，记录日志并输出到日志框。"""
        full_message = f"{context}\n{traceback.format_exc()}"
        logging.error(full_message)
        self.safe_log(full_message)

    # ----------------- 主Tab布局 -----------------
    def build_main_tab(self):
        """
        主Tab包含左侧的“本章内容”编辑框和输出日志，以及右侧的主要操作和参数设置区
        """
        self.main_tab.rowconfigure(0, weight=1)
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.columnconfigure(1, weight=0)

        self.left_frame = ctk.CTkFrame(self.main_tab)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.right_frame = ctk.CTkFrame(self.main_tab)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

        self.build_left_layout()
        self.build_right_layout()

    def build_left_layout(self):
        """
        左侧区域：本章内容(可编辑) + Step流程按钮 + 输出日志(只读)
        """
        self.left_frame.grid_rowconfigure(0, weight=0)
        self.left_frame.grid_rowconfigure(1, weight=2)
        self.left_frame.grid_rowconfigure(2, weight=0)
        self.left_frame.grid_rowconfigure(3, weight=0)
        self.left_frame.grid_rowconfigure(4, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        chapter_label = ctk.CTkLabel(self.left_frame, text="本章内容 (可编辑)", font=("Microsoft YaHei", 12))
        chapter_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

        # 章节文本编辑框
        self.chapter_result = ctk.CTkTextbox(self.left_frame, wrap="word", font=("Microsoft YaHei", 14))
        TextWidgetContextMenu(self.chapter_result)
        self.chapter_result.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))

        # Step 按钮区域
        self.step_buttons_frame = ctk.CTkFrame(self.left_frame)
        self.step_buttons_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.step_buttons_frame.columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_generate_architecture = ctk.CTkButton(
            self.step_buttons_frame,
            text="Step1. 生成架构",
            command=self.generate_novel_architecture_ui,
            font=("Microsoft YaHei", 12)
        )
        self.btn_generate_architecture.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

        self.btn_generate_directory = ctk.CTkButton(
            self.step_buttons_frame,
            text="Step2. 生成目录",
            command=self.generate_chapter_blueprint_ui,
            font=("Microsoft YaHei", 12)
        )
        self.btn_generate_directory.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        self.btn_generate_chapter = ctk.CTkButton(
            self.step_buttons_frame,
            text="Step3. 生成草稿",
            command=self.generate_chapter_draft_ui,
            font=("Microsoft YaHei", 12)
        )
        self.btn_generate_chapter.grid(row=0, column=2, padx=5, pady=2, sticky="ew")

        self.btn_finalize_chapter = ctk.CTkButton(
            self.step_buttons_frame,
            text="Step4. 定稿章节",
            command=self.finalize_chapter_ui,
            font=("Microsoft YaHei", 12)
        )
        self.btn_finalize_chapter.grid(row=0, column=3, padx=5, pady=2, sticky="ew")

        # 日志文本框
        log_label = ctk.CTkLabel(self.left_frame, text="输出日志 (只读)", font=("Microsoft YaHei", 12))
        log_label.grid(row=3, column=0, padx=5, pady=(5, 0), sticky="w")

        self.log_text = ctk.CTkTextbox(self.left_frame, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.log_text)
        self.log_text.grid(row=4, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.log_text.configure(state="disabled")

    def build_right_layout(self):
        """
        右侧区域：配置区(tabview) + 小说主参数 + 可选功能按钮
        """
        self.right_frame.grid_rowconfigure(0, weight=0)
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_rowconfigure(2, weight=0)
        self.right_frame.columnconfigure(0, weight=1)

        # 配置区（AI/Embedding）
        self.config_frame = ctk.CTkFrame(self.right_frame, corner_radius=10, border_width=2, border_color="gray")
        self.config_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.config_frame.columnconfigure(0, weight=1)

        self.build_config_tabview()

        # 小说参数（主题、类型、章节数、字数、保存路径、可选元素等）
        self.build_novel_params_area(start_row=1)

        # 可选功能按钮（一致性审校、导入知识库、清空向量库、查看剧情要点）
        self.build_optional_buttons_area(start_row=2)

    # ----------------- 配置TabView -----------------
    def build_config_tabview(self):
        """
        创建包含 LLM Model settings 和 Embedding settings 的选项卡。
        """
        self.config_tabview = ctk.CTkTabview(self.config_frame)
        self.config_tabview.grid(row=0, column=0, sticky="we", padx=5, pady=5)

        self.ai_config_tab = self.config_tabview.add("LLM Model settings")
        self.embeddings_config_tab = self.config_tabview.add("Embedding settings")
        

        self.build_ai_config_tab()
        self.build_embeddings_config_tab()

        # 底部的“保存配置”和“加载配置”按钮
        self.btn_frame_config = ctk.CTkFrame(self.config_frame)
        self.btn_frame_config.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.btn_frame_config.columnconfigure(0, weight=1)
        self.btn_frame_config.columnconfigure(1, weight=1)

        save_config_btn = ctk.CTkButton(self.btn_frame_config, text="保存配置", command=self.save_config_btn, font=("Microsoft YaHei", 12))
        save_config_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        load_config_btn = ctk.CTkButton(self.btn_frame_config, text="加载配置", command=self.load_config_btn, font=("Microsoft YaHei", 12))
        load_config_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    def create_label_with_help(self, parent, label_text, tooltip_key, row, column,
                               font=None, sticky="e", padx=5, pady=5):
        """
        封装一个带“?”按钮的Label，用于展示提示信息。
        """
        frame = ctk.CTkFrame(parent)
        frame.grid(row=row, column=column, padx=padx, pady=pady, sticky=sticky)
        frame.columnconfigure(0, weight=0)

        label = ctk.CTkLabel(frame, text=label_text, font=font)
        label.pack(side="left")

        btn = ctk.CTkButton(
            frame,
            text="?",
            width=22,
            height=22,
            font=("Microsoft YaHei", 10),
            command=lambda: self.show_tooltip(tooltip_key)
        )
        btn.pack(side="left", padx=3)

        return frame

    # --------------- LLM 模型配置 ---------------
    def build_ai_config_tab(self):
        def on_interface_format_changed(new_value):
            """
            当切换LLM接口格式时，自动设置base_url为对应的默认值。
            """
            if new_value == "Ollama":
                self.base_url_var.set("http://localhost:11434/v1")
            elif new_value == "ML Studio":
                self.base_url_var.set("http://localhost:1234/v1")
            elif new_value == "OpenAI":
                self.base_url_var.set("https://api.openai.com/v1")
            elif new_value == "Azure OpenAI":
                self.base_url_var.set("https://[az].openai.azure.com/openai/deployments/[model]/chat/completions?api-version=2024-08-01-preview")
            elif new_value == "DeepSeek":
                self.base_url_var.set("https://api.deepseek.com/v1")
            elif new_value == "Gemini":
                self.base_url_var.set("")  # Gemini 通常不需要 Base URL，可以设置为空

        for i in range(7):
            self.ai_config_tab.grid_rowconfigure(i, weight=0)
        self.ai_config_tab.grid_columnconfigure(0, weight=0)
        self.ai_config_tab.grid_columnconfigure(1, weight=1)
        self.ai_config_tab.grid_columnconfigure(2, weight=0)

        # 1) API Key
        self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="LLM API Key:",
            tooltip_key="api_key",
            row=0,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        api_key_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.api_key_var, font=("Microsoft YaHei", 12), show="*")
        api_key_entry.grid(row=0, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

        # 2) Base URL
        self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="LLM Base URL:",
            tooltip_key="base_url",
            row=1,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        base_url_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.base_url_var, font=("Microsoft YaHei", 12))
        base_url_entry.grid(row=1, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

        # 3) 接口格式
        label_frame = self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="LLM 接口格式:",
            tooltip_key="interface_format",
            row=2,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        interface_options = ["DeepSeek", "OpenAI", "Azure OpenAI", "Ollama", "ML Studio", "Gemini"]
        interface_dropdown = ctk.CTkOptionMenu(
            self.ai_config_tab,
            values=interface_options,
            variable=self.interface_format_var,
            command=on_interface_format_changed,
            font=("Microsoft YaHei", 12)
        )
        interface_dropdown.grid(row=2, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

        # 4) Model Name
        self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="Model Name:",
            tooltip_key="model_name",
            row=3,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        model_name_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.model_name_var, font=("Microsoft YaHei", 12))
        model_name_entry.grid(row=3, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

        # 5) Temperature
        temp_frame = self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="Temperature:",
            tooltip_key="temperature",
            row=4,
            column=0,
            font=("Microsoft YaHei", 12)
        )

        def update_temp_label(value):
            self.temp_value_label.configure(text=f"{float(value):.2f}")

        temp_scale = ctk.CTkSlider(
            self.ai_config_tab,
            from_=0.0, to=2.0,
            number_of_steps=200,
            command=update_temp_label,
            variable=self.temperature_var
        )
        temp_scale.grid(row=4, column=1, padx=5, pady=5, sticky="we")

        self.temp_value_label = ctk.CTkLabel(
            self.ai_config_tab,
            text=f"{self.temperature_var.get():.2f}",
            font=("Microsoft YaHei", 12)
        )
        self.temp_value_label.grid(row=4, column=2, padx=5, pady=5, sticky="w")

        # 6) Max Tokens
        self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="Max Tokens:",
            tooltip_key="max_tokens",
            row=5,
            column=0,
            font=("Microsoft YaHei", 12)
        )

        def update_max_tokens_label(value):
            self.max_tokens_value_label.configure(text=str(int(float(value))))

        max_tokens_slider = ctk.CTkSlider(
            self.ai_config_tab,
            from_=0,
            to=102400,
            number_of_steps=100,
            command=update_max_tokens_label,
            variable=self.max_tokens_var
        )
        max_tokens_slider.grid(row=5, column=1, padx=5, pady=5, sticky="we")

        self.max_tokens_value_label = ctk.CTkLabel(
            self.ai_config_tab,
            text=str(self.max_tokens_var.get()),
            font=("Microsoft YaHei", 12)
        )
        self.max_tokens_value_label.grid(row=5, column=2, padx=5, pady=5, sticky="w")

        # 7) Timeout (sec)
        self.create_label_with_help(
            parent=self.ai_config_tab,
            label_text="Timeout (sec):",
            tooltip_key="timeout",
            row=6,
            column=0,
            font=("Microsoft YaHei", 12)
        )

        def update_timeout_label(value):
            integer_val = int(float(value))
            self.timeout_value_label.configure(text=str(integer_val))

        timeout_slider = ctk.CTkSlider(
            self.ai_config_tab,
            from_=0,
            to=3600,
            number_of_steps=3600,
            command=update_timeout_label,
            variable=self.timeout_var
        )
        timeout_slider.grid(row=6, column=1, padx=5, pady=5, sticky="we")

        self.timeout_value_label = ctk.CTkLabel(
            self.ai_config_tab,
            text=str(self.timeout_var.get()),
            font=("Microsoft YaHei", 12)
        )
        self.timeout_value_label.grid(row=6, column=2, padx=5, pady=5, sticky="w")

        # 添加测试按钮
        test_btn = ctk.CTkButton(
            self.ai_config_tab,
            text="测试配置",
            command=self.test_llm_config,
            font=("Microsoft YaHei", 12)
        )
        test_btn.grid(row=7, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

    # --------------- Embedding 模型配置 ---------------
    def build_embeddings_config_tab(self):
        def on_embedding_interface_changed(new_value):
            """
            当切换Embedding接口格式时，自动设置embedding_url为对应的默认值。
            """
            if new_value == "Ollama":
                self.embedding_url_var.set("http://localhost:11434/api")
            elif new_value == "ML Studio":
                self.embedding_url_var.set("http://localhost:1234/v1")
            elif new_value == "OpenAI":
                self.embedding_url_var.set("https://api.openai.com/v1")
                self.embedding_model_name_var.set("text-embedding-ada-002")
            elif new_value == "Azure OpenAI":
                self.embedding_url_var.set("https://[az].openai.azure.com/openai/deployments/[model]/embeddings?api-version=2023-05-15")
            elif new_value == "DeepSeek":
                self.embedding_url_var.set("https://api.deepseek.com/v1")
            elif new_value == "Gemini":
                self.embedding_url_var.set("https://generativelanguage.googleapis.com/v1beta/")
                self.embedding_model_name_var.set("models/text-embedding-004")

        for i in range(5):
            self.embeddings_config_tab.grid_rowconfigure(i, weight=0)
        self.embeddings_config_tab.grid_columnconfigure(0, weight=0)
        self.embeddings_config_tab.grid_columnconfigure(1, weight=1)
        self.embeddings_config_tab.grid_columnconfigure(2, weight=0)

        # 1) Embedding API Key
        self.create_label_with_help(
            parent=self.embeddings_config_tab,
            label_text="Embedding API Key:",
            tooltip_key="embedding_api_key",
            row=0,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        emb_api_key_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_api_key_var, font=("Microsoft YaHei", 12), show="*")
        emb_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        # 2) Embedding 接口格式
        self.create_label_with_help(
            parent=self.embeddings_config_tab,
            label_text="Embedding 接口格式:",
            tooltip_key="embedding_interface_format",
            row=1,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        emb_interface_options = ["DeepSeek", "OpenAI", "Azure OpenAI", "Gemini", "Ollama", "ML Studio"]
        emb_interface_dropdown = ctk.CTkOptionMenu(
            self.embeddings_config_tab,
            values=emb_interface_options,
            variable=self.embedding_interface_format_var,
            command=on_embedding_interface_changed,
            font=("Microsoft YaHei", 12)
        )
        emb_interface_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        # 3) Embedding Base URL
        self.create_label_with_help(
            parent=self.embeddings_config_tab,
            label_text="Embedding Base URL:",
            tooltip_key="embedding_url",
            row=2,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        emb_url_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_url_var, font=("Microsoft YaHei", 12))
        emb_url_entry.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

        # 4) Embedding Model Name
        self.create_label_with_help(
            parent=self.embeddings_config_tab,
            label_text="Embedding Model Name:",
            tooltip_key="embedding_model_name",
            row=3,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        emb_model_name_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_model_name_var, font=("Microsoft YaHei", 12))
        emb_model_name_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

        # 5) Retrieval Top-K
        self.create_label_with_help(
            parent=self.embeddings_config_tab,
            label_text="Retrieval Top-K:",
            tooltip_key="embedding_retrieval_k",
            row=4,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        emb_retrieval_k_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_retrieval_k_var, font=("Microsoft YaHei", 12))
        emb_retrieval_k_entry.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")

        # 添加测试按钮
        test_btn = ctk.CTkButton(
            self.embeddings_config_tab,
            text="测试配置",
            command=self.test_embedding_config,
            font=("Microsoft YaHei", 12)
        )
        test_btn.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

    # ----------------- 小说参数区 -----------------
    def build_novel_params_area(self, start_row=1):
        """
        在右侧 frame 中创建：主题、类型、章节数/字数、保存路径、本章指导、可选要素等参数输入区。
        """
        self.params_frame = ctk.CTkScrollableFrame(self.right_frame, orientation="vertical")
        self.params_frame.grid(row=start_row, column=0, sticky="nsew", padx=5, pady=5)
        self.params_frame.columnconfigure(1, weight=1)
        
        # def on_language_changed(new_value):
        #     """
        #     当切换语言时,设置对应值。
        #     """
        #     self.chapter_lang_format_var.set(new_value)         
        
      
        # 1) 主题(Topic)
        topic_label_frame = self.create_label_with_help(
            parent=self.params_frame,
            label_text="主题(Topic):",
            tooltip_key="topic",
            row=0,
            column=0,
            font=("Microsoft YaHei", 12),
            sticky="ne"
        )
        self.topic_text = ctk.CTkTextbox(self.params_frame, height=80, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.topic_text)
        self.topic_text.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        if self.topic_default:
            self.topic_text.insert("0.0", self.topic_default)

        # 2) 类型(Genre)
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="类型(Genre):",
            tooltip_key="genre",
            row=1,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        genre_entry = ctk.CTkEntry(self.params_frame, textvariable=self.genre_var, font=("Microsoft YaHei", 12))
        genre_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # 3) 章节数 & 每章字数
        row_for_chapter_and_word = 2
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="章节数 & 每章字数:",
            tooltip_key="num_chapters",
            row=row_for_chapter_and_word,
            column=0,
            font=("Microsoft YaHei", 12)
        )

        chapter_word_frame = ctk.CTkFrame(self.params_frame)
        chapter_word_frame.grid(row=row_for_chapter_and_word, column=1, padx=5, pady=5, sticky="ew")
        chapter_word_frame.columnconfigure((0, 1, 2, 3), weight=0)

        num_chapters_label = ctk.CTkLabel(chapter_word_frame, text="章节数:", font=("Microsoft YaHei", 12))
        num_chapters_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        num_chapters_entry = ctk.CTkEntry(chapter_word_frame, textvariable=self.num_chapters_var, width=60, font=("Microsoft YaHei", 12))
        num_chapters_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        word_number_label = ctk.CTkLabel(chapter_word_frame, text="每章字数:", font=("Microsoft YaHei", 12))
        word_number_label.grid(row=0, column=2, padx=(15, 5), pady=5, sticky="e")

        word_number_entry = ctk.CTkEntry(chapter_word_frame, textvariable=self.word_number_var, width=60, font=("Microsoft YaHei", 12))
        word_number_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        # 4) 保存路径
        row_fp = 3
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="保存路径:",
            tooltip_key="filepath",
            row=row_fp,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        self.filepath_frame = ctk.CTkFrame(self.params_frame)
        self.filepath_frame.grid(row=row_fp, column=1, padx=5, pady=5, sticky="nsew")
        self.filepath_frame.columnconfigure(0, weight=1)

        filepath_entry = ctk.CTkEntry(self.filepath_frame, textvariable=self.filepath_var, font=("Microsoft YaHei", 12))
        filepath_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        browse_btn = ctk.CTkButton(self.filepath_frame, text="浏览...", command=self.browse_folder, width=60, font=("Microsoft YaHei", 12))
        browse_btn.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        # 5) 章节号
        row_chap_num = 4
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="章节号:",
            tooltip_key="chapter_num",
            row=row_chap_num,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        chapter_num_entry = ctk.CTkEntry(self.params_frame, textvariable=self.chapter_num_var, width=80, font=("Microsoft YaHei", 12))
        chapter_num_entry.grid(row=row_chap_num, column=1, padx=5, pady=5, sticky="w")

        # 6) 本章要求
        row_user_guide = 5
        guide_label_frame = self.create_label_with_help(
            parent=self.params_frame,
            label_text="本章要求:",
            tooltip_key="user_guidance",
            row=row_user_guide,
            column=0,
            font=("Microsoft YaHei", 12),
            sticky="ne"
        )
        self.user_guide_text = ctk.CTkTextbox(self.params_frame, height=80, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.user_guide_text)
        self.user_guide_text.grid(row=row_user_guide, column=1, padx=5, pady=5, sticky="nsew")
        # 如果配置文件里有保存过本章指导，则恢复
        if self.user_guidance_default:
            self.user_guide_text.insert("0.0", self.user_guidance_default)

        # 7) 可选元素：核心人物/关键道具/空间坐标/时间压力
        row_idx = 6
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="核心人物:",
            tooltip_key="characters_involved",
            row=row_idx,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        char_inv_entry = ctk.CTkEntry(self.params_frame, textvariable=self.characters_involved_var, font=("Microsoft YaHei", 12))
        char_inv_entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
        row_idx += 1

        self.create_label_with_help(
            parent=self.params_frame,
            label_text="关键道具:",
            tooltip_key="key_items",
            row=row_idx,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        key_items_entry = ctk.CTkEntry(self.params_frame, textvariable=self.key_items_var, font=("Microsoft YaHei", 12))
        key_items_entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
        row_idx += 1

        self.create_label_with_help(
            parent=self.params_frame,
            label_text="空间坐标:",
            tooltip_key="scene_location",
            row=row_idx,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        scene_loc_entry = ctk.CTkEntry(self.params_frame, textvariable=self.scene_location_var, font=("Microsoft YaHei", 12))
        scene_loc_entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
        row_idx += 1

        self.create_label_with_help(
            parent=self.params_frame,
            label_text="时间压力:",
            tooltip_key="time_constraint",
            row=row_idx,
            column=0,
            font=("Microsoft YaHei", 12)
        )
        time_const_entry = ctk.CTkEntry(self.params_frame, textvariable=self.time_constraint_var, font=("Microsoft YaHei", 12))
        time_const_entry.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")        
        row_idx += 1
        
         # 8) 生成章节内容的语言(Language)
        self.create_label_with_help(
            parent=self.params_frame,
            label_text="章节内容的语言:",
            tooltip_key="language",
            row=row_idx,
            column=0,
            font=("Microsoft YaHei", 12),
            sticky="ne"
        )
        chapter_lang_options = ["中文", "英文"]
        chapter_lang_dropdown = ctk.CTkOptionMenu(
            self.params_frame,
            values=chapter_lang_options,
            variable=self.chapter_lang_format_var,
            # command=on_language_changed,
            font=("Microsoft YaHei", 12)
        )
        chapter_lang_dropdown.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")

    # ----------------- 可选功能按钮 -----------------
    def build_optional_buttons_area(self, start_row=2):
        """
        包含：一致性审校、导入知识库、清空向量库、查看剧情要点。
        """
        self.optional_btn_frame = ctk.CTkFrame(self.right_frame)
        self.optional_btn_frame.grid(row=start_row, column=0, sticky="ew", padx=5, pady=5)
        self.optional_btn_frame.columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_check_consistency = ctk.CTkButton(
            self.optional_btn_frame,
            text="一致性审校",
            command=self.do_consistency_check,
            font=("Microsoft YaHei", 12)
        )
        self.btn_check_consistency.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.btn_import_knowledge = ctk.CTkButton(
            self.optional_btn_frame,
            text="导入知识库",
            command=self.import_knowledge_handler,
            font=("Microsoft YaHei", 12)
        )
        self.btn_import_knowledge.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_clear_vectorstore = ctk.CTkButton(
            self.optional_btn_frame,
            text="清空向量库",
            fg_color="red",
            command=self.clear_vectorstore_handler,
            font=("Microsoft YaHei", 12)
        )
        self.btn_clear_vectorstore.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.plot_arcs_btn = ctk.CTkButton(
            self.optional_btn_frame,
            text="查看剧情要点",
            command=self.show_plot_arcs_ui,
            font=("Microsoft YaHei", 12)
        )
        self.plot_arcs_btn.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

    # ----------------- 配置的加载与保存 -----------------
    def load_config_btn(self):
        """
        从 config.json 中加载配置，并更新界面显示
        """
        cfg = load_config(self.config_file)
        if cfg:
            self.api_key_var.set(cfg.get("api_key", ""))
            self.base_url_var.set(cfg.get("base_url", ""))
            self.interface_format_var.set(cfg.get("interface_format", "OpenAI"))
            self.model_name_var.set(cfg.get("model_name", ""))
            self.temperature_var.set(cfg.get("temperature", 0.7))
            self.max_tokens_var.set(cfg.get("max_tokens", 2048))
            self.timeout_var.set(cfg.get("timeout", 600))

            self.embedding_api_key_var.set(cfg.get("embedding_api_key", ""))
            self.embedding_interface_format_var.set(cfg.get("embedding_interface_format", "OpenAI"))
            self.embedding_url_var.set(cfg.get("embedding_url", ""))
            self.embedding_model_name_var.set(cfg.get("embedding_model_name", ""))
            self.embedding_retrieval_k_var.set(str(cfg.get("embedding_retrieval_k", 4)))

            self.genre_var.set(cfg.get("genre", ""))
            self.num_chapters_var.set(str(cfg.get("num_chapters", 10)))
            self.word_number_var.set(str(cfg.get("word_number", 3000)))
            self.filepath_var.set(cfg.get("filepath", ""))

            topic_value = cfg.get("topic", "")
            self.topic_text.delete("0.0", "end")
            self.topic_text.insert("0.0", topic_value)

            # 新增：读取章节号、本章指导、可选元素
            self.chapter_num_var.set(str(cfg.get("chapter_num", "1")))

            user_guidance_value = cfg.get("user_guidance", "")
            self.user_guide_text.delete("0.0", "end")
            self.user_guide_text.insert("0.0", user_guidance_value)

            self.characters_involved_var.set(cfg.get("characters_involved", ""))
            self.key_items_var.set(cfg.get("key_items", ""))
            self.scene_location_var.set(cfg.get("scene_location", ""))
            self.time_constraint_var.set(cfg.get("time_constraint", ""))
            self.chapter_lang_format_var.set(cfg.get("chapter_lang_format", "中文"))

            self.log("已加载配置。")
        else:
            messagebox.showwarning("提示", "未找到或无法读取配置文件。")

    def save_config_btn(self):
        """
        将当前界面的配置信息保存到 config.json
        """
        config_data = {
            "api_key": self.api_key_var.get(),
            "base_url": self.base_url_var.get(),
            "interface_format": self.interface_format_var.get(),
            "model_name": self.model_name_var.get(),
            "temperature": self.temperature_var.get(),
            "max_tokens": self.max_tokens_var.get(),
            "timeout": self.safe_get_int(self.timeout_var, 600),

            "embedding_api_key": self.embedding_api_key_var.get(),
            "embedding_interface_format": self.embedding_interface_format_var.get(),
            "embedding_url": self.embedding_url_var.get(),
            "embedding_model_name": self.embedding_model_name_var.get(),
            "embedding_retrieval_k": self.safe_get_int(self.embedding_retrieval_k_var, 4),

            "topic": self.topic_text.get("0.0", "end").strip(),
            "genre": self.genre_var.get(),
            "num_chapters": self.safe_get_int(self.num_chapters_var, 10),
            "word_number": self.safe_get_int(self.word_number_var, 3000),
            "filepath": self.filepath_var.get(),

            # 新增：章节号、本章指导、可选要素
            "chapter_num": self.chapter_num_var.get(),
            "user_guidance": self.user_guide_text.get("0.0", "end").strip(),
            "characters_involved": self.characters_involved_var.get(),
            "key_items": self.key_items_var.get(),
            "scene_location": self.scene_location_var.get(),
            "time_constraint": self.time_constraint_var.get(),
            "chapter_lang_format": self.chapter_lang_format_var.get()
        }

        if save_config(config_data, self.config_file):
            messagebox.showinfo("提示", "配置已保存至 config.json")
            self.log("配置已保存。")
        else:
            messagebox.showerror("错误", "保存配置失败。")

    def browse_folder(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.filepath_var.set(selected_dir)

    # ----------------- 生成与定稿的函数 -----------------
    def generate_novel_architecture_ui(self):
        """
        Step1：生成小说整体架构
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先选择保存文件路径")
            return

        def task():
            self.disable_button_safe(self.btn_generate_architecture)
            try:
                interface_format = self.interface_format_var.get().strip()
                api_key = self.api_key_var.get().strip()
                base_url = self.base_url_var.get().strip()
                model_name = self.model_name_var.get().strip()
                temperature = self.temperature_var.get()
                max_tokens = self.max_tokens_var.get()
                timeout_val = self.safe_get_int(self.timeout_var, 600)

                topic = self.topic_text.get("0.0", "end").strip()
                genre = self.genre_var.get().strip()
                num_chapters = self.safe_get_int(self.num_chapters_var, 10)
                word_number = self.safe_get_int(self.word_number_var, 3000)

                self.safe_log("开始生成小说架构...")
                Novel_architecture_generate(
                    interface_format=interface_format,
                    api_key=api_key,
                    base_url=base_url,
                    llm_model=model_name,
                    topic=topic,
                    genre=genre,
                    number_of_chapters=num_chapters,
                    word_number=word_number,
                    filepath=filepath,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_val
                )
                self.safe_log("✅ 小说架构生成完成。请在 'Novel Architecture' 标签页查看或编辑。")
            except Exception:
                self.handle_exception("生成小说架构时出错")
            finally:
                self.enable_button_safe(self.btn_generate_architecture)

        threading.Thread(target=task, daemon=True).start()

    def generate_chapter_blueprint_ui(self):
        """
        Step2：生成章节蓝图
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先选择保存文件路径")
            return

        def task():
            self.disable_button_safe(self.btn_generate_directory)
            try:
                interface_format = self.interface_format_var.get().strip()
                api_key = self.api_key_var.get().strip()
                base_url = self.base_url_var.get().strip()
                model_name = self.model_name_var.get().strip()
                number_of_chapters = self.safe_get_int(self.num_chapters_var, 10)
                temperature = self.temperature_var.get()
                max_tokens = self.max_tokens_var.get()
                timeout_val = self.safe_get_int(self.timeout_var, 600)

                self.safe_log("开始生成章节蓝图...")
                Chapter_blueprint_generate(
                    interface_format=interface_format,
                    api_key=api_key,
                    base_url=base_url,
                    llm_model=model_name,
                    number_of_chapters=number_of_chapters,
                    filepath=filepath,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_val
                )
                self.safe_log("✅ 章节蓝图生成完成。请在 'Chapter Blueprint' 标签页查看或编辑。")
            except Exception:
                self.handle_exception("生成章节蓝图时出错")
            finally:
                self.enable_button_safe(self.btn_generate_directory)

        threading.Thread(target=task, daemon=True).start()

    def generate_chapter_draft_ui(self):
        """
        Step3：生成章节草稿
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先配置保存文件路径。")
            return

        def task():
            self.disable_button_safe(self.btn_generate_chapter)
            try:
                interface_format = self.interface_format_var.get().strip()
                api_key = self.api_key_var.get().strip()
                base_url = self.base_url_var.get().strip()
                model_name = self.model_name_var.get().strip()
                temperature = self.temperature_var.get()
                max_tokens = self.max_tokens_var.get()
                timeout_val = self.safe_get_int(self.timeout_var, 600)

                chap_num = self.safe_get_int(self.chapter_num_var, 1)
                word_number = self.safe_get_int(self.word_number_var, 3000)
                user_guidance = self.user_guide_text.get("0.0", "end").strip()

                char_inv = self.characters_involved_var.get().strip()
                key_items = self.key_items_var.get().strip()
                scene_loc = self.scene_location_var.get().strip()
                time_constr = self.time_constraint_var.get().strip()
                chapter_lang_format = self.chapter_lang_format_var.get().strip()
                

                embedding_api_key = self.embedding_api_key_var.get().strip()
                embedding_url = self.embedding_url_var.get().strip()
                embedding_interface_format = self.embedding_interface_format_var.get().strip()
                embedding_model_name = self.embedding_model_name_var.get().strip()
                embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

                self.safe_log(f"开始生成第{chap_num}章草稿...")
                draft_text = generate_chapter_draft(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    filepath=filepath,
                    novel_number=chap_num,
                    word_number=word_number,
                    temperature=temperature,
                    user_guidance=user_guidance,
                    characters_involved=char_inv,
                    key_items=key_items,
                    scene_location=scene_loc,
                    time_constraint=time_constr,
                    embedding_api_key=embedding_api_key,
                    embedding_url=embedding_url,
                    embedding_interface_format=embedding_interface_format,
                    embedding_model_name=embedding_model_name,
                    embedding_retrieval_k=embedding_k,
                    interface_format=interface_format,
                    max_tokens=max_tokens,
                    timeout=timeout_val,
                    chapter_lang_format=chapter_lang_format
                )
                if draft_text:
                    self.safe_log(f"✅ 第{chap_num}章草稿生成完成。请在左侧查看或编辑。")
                    self.master.after(0, lambda: self.show_chapter_in_textbox(draft_text))
                else:
                    self.safe_log("⚠️ 本章草稿生成失败或无内容。")

            except Exception:
                self.handle_exception("生成章节草稿时出错")
            finally:
                self.enable_button_safe(self.btn_generate_chapter)

        threading.Thread(target=task, daemon=True).start()

    def show_chapter_in_textbox(self, text: str):
        """
        将生成或读取到的章节文本内容显示到左侧文本框中。
        """
        self.chapter_result.delete("0.0", "end")
        self.chapter_result.insert("0.0", text)
        self.chapter_result.see("end")

    def finalize_chapter_ui(self):
        """
        Step4：定稿章节，更新全局摘要、角色状态、向量库等。
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先配置保存文件路径。")
            return

        def task():
            self.disable_button_safe(self.btn_finalize_chapter)
            try:
                interface_format = self.interface_format_var.get().strip()
                api_key = self.api_key_var.get().strip()
                base_url = self.base_url_var.get().strip()
                model_name = self.model_name_var.get().strip()
                temperature = self.temperature_var.get()
                max_tokens = self.max_tokens_var.get()
                timeout_val = self.safe_get_int(self.timeout_var, 600)

                embedding_api_key = self.embedding_api_key_var.get().strip()
                embedding_url = self.embedding_url_var.get().strip()
                embedding_interface_format = self.embedding_interface_format_var.get().strip()
                embedding_model_name = self.embedding_model_name_var.get().strip()

                chap_num = self.safe_get_int(self.chapter_num_var, 1)
                word_number = self.safe_get_int(self.word_number_var, 3000)

                self.safe_log(f"开始定稿第{chap_num}章...")

                # 先读取用户在文本框中编辑好的内容
                chapters_dir = os.path.join(filepath, "chapters")
                os.makedirs(chapters_dir, exist_ok=True)
                chapter_file = os.path.join(chapters_dir, f"chapter_{chap_num}.txt")

                edited_text = self.chapter_result.get("0.0", "end").strip()
                
                word_counter = self.count_chinese_and_english(edited_text)
                self.safe_log("当前章节字数: " + str(word_counter))
                
                # 如果字数不足90%，询问是否扩写
                if word_counter < 0.8 * word_number:
                    ask = messagebox.askyesno(
                        "字数不足",
                        f"当前章节字数 ({word_counter}) 低于目标字数({word_number})的70%，是否要尝试扩写？"
                    )
                    if ask:
                        # 调用 enrich_chapter_text 进行扩写
                        self.safe_log("正在扩写章节内容...")
                        enriched = enrich_chapter_text(
                            chapter_text=edited_text,
                            word_number=word_number,
                            api_key=api_key,
                            base_url=base_url,
                            model_name=model_name,
                            temperature=temperature,
                            interface_format=interface_format,
                            max_tokens=max_tokens,
                            timeout=timeout_val
                        )
                        edited_text = enriched
                        # 更新文本框显示
                        self.master.after(0, lambda: self.chapter_result.delete("0.0", "end"))
                        self.master.after(0, lambda: self.chapter_result.insert("0.0", edited_text))

                # 将（可能已扩写的）文本保存到本地文件
                clear_file_content(chapter_file)
                save_string_to_txt(edited_text, chapter_file)

                # 调用 finalize_chapter 做最终处理（更新全局摘要、角色状态、向量库等）
                finalize_chapter(
                    novel_number=chap_num,
                    word_number=word_number,
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    filepath=filepath,
                    embedding_api_key=embedding_api_key,
                    embedding_url=embedding_url,
                    embedding_interface_format=embedding_interface_format,
                    embedding_model_name=embedding_model_name,
                    interface_format=interface_format,
                    max_tokens=max_tokens,
                    timeout=timeout_val
                )
                self.safe_log(f"✅ 第{chap_num}章定稿完成（已更新全局摘要、角色状态、向量库）。")

                final_text = read_file(chapter_file)
                self.master.after(0, lambda: self.show_chapter_in_textbox(final_text))

            except Exception:
                self.handle_exception("定稿章节时出错")
            finally:
                self.enable_button_safe(self.btn_finalize_chapter)

        threading.Thread(target=task, daemon=True).start()

    # ----------------- 一致性审校 -----------------
    def do_consistency_check(self):
        """
        可选功能：对当前章节进行一致性审校，基于全局摘要和角色状态等进行检查。
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先配置保存文件路径。")
            return

        def task():
            self.disable_button_safe(self.btn_check_consistency)
            try:
                api_key = self.api_key_var.get().strip()
                base_url = self.base_url_var.get().strip()
                model_name = self.model_name_var.get().strip()
                temperature = self.temperature_var.get()
                interface_format = self.interface_format_var.get()
                max_tokens = self.max_tokens_var.get()
                timeout = self.timeout_var.get()

                chap_num = self.safe_get_int(self.chapter_num_var, 1)
                chap_file = os.path.join(filepath, "chapters", f"chapter_{chap_num}.txt")
                chapter_text = read_file(chap_file)

                if not chapter_text.strip():
                    self.safe_log("⚠️ 当前章节文件为空或不存在，无法审校。")
                    return

                self.safe_log("开始一致性审校...")
                result = check_consistency(
                    novel_setting="",
                    character_state=read_file(os.path.join(filepath, "character_state.txt")),
                    global_summary=read_file(os.path.join(filepath, "global_summary.txt")),
                    chapter_text=chapter_text,
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    interface_format=interface_format,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    plot_arcs=""
                )
                self.safe_log("审校结果：")
                self.safe_log(result)

            except Exception:
                self.handle_exception("审校时出错")
            finally:
                self.enable_button_safe(self.btn_check_consistency)

        threading.Thread(target=task, daemon=True).start()

    # ----------------- 知识库操作 -----------------
    def import_knowledge_handler(self):
        """
        导入文本文件到本地知识库，供后续生成章节时的检索。
        """
        selected_file = filedialog.askopenfilename(
            title="选择要导入的知识库文件",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if selected_file:
            def task():
                self.disable_button_safe(self.btn_import_knowledge)
                try:
                    emb_api_key = self.embedding_api_key_var.get().strip()
                    emb_url = self.embedding_url_var.get().strip()
                    emb_format = self.embedding_interface_format_var.get().strip()
                    emb_model = self.embedding_model_name_var.get().strip()

                    self.safe_log(f"开始导入知识库文件: {selected_file}")
                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=selected_file,
                        filepath=self.filepath_var.get().strip()
                    )
                    self.safe_log("✅ 知识库文件导入完成。")
                except Exception:
                    self.handle_exception("导入知识库时出错")
                finally:
                    self.enable_button_safe(self.btn_import_knowledge)

            threading.Thread(target=task, daemon=True).start()

    def clear_vectorstore_handler(self):
        """
        清空本地向量库文件夹。
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先配置保存文件路径。")
            return

        first_confirm = messagebox.askyesno("警告", "确定要清空本地向量库吗？此操作不可恢复！")
        if first_confirm:
            second_confirm = messagebox.askyesno("二次确认", "你确定真的要删除所有向量数据吗？此操作不可恢复！")
            if second_confirm:
                if clear_vector_store(filepath):
                    self.log("已清空向量库。")
                else:
                    self.log(f"未能清空向量库，请关闭程序后手动删除 {filepath} 下的 vectorstore 文件夹。")

    def show_plot_arcs_ui(self):
        """
        查看剧情要点/未解决冲突的记录（plot_arcs.txt）。
        """
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先在主Tab中设置保存文件路径")
            return

        plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
        if not os.path.exists(plot_arcs_file):
            messagebox.showinfo("剧情要点", "当前还未生成任何剧情要点或冲突记录。")
            return

        arcs_text = read_file(plot_arcs_file).strip()
        if not arcs_text:
            arcs_text = "当前没有记录的剧情要点或冲突。"

        top = ctk.CTkToplevel(self.master)
        top.title("剧情要点/未解决冲突")
        top.geometry("600x400")

        text_area = ctk.CTkTextbox(top, wrap="word", font=("Microsoft YaHei", 12))
        text_area.pack(fill="both", expand=True, padx=10, pady=10)

        text_area.insert("0.0", arcs_text)
        text_area.configure(state="disabled")

    # ----------------- Novel Architecture 标签页 -----------------
    def build_setting_tab(self):
        self.setting_tab.rowconfigure(0, weight=0)
        self.setting_tab.rowconfigure(1, weight=1)
        self.setting_tab.columnconfigure(0, weight=1)

        load_btn = ctk.CTkButton(
            self.setting_tab,
            text="加载 Novel_architecture.txt",
            command=self.load_novel_architecture,
            font=("Microsoft YaHei", 12)
        )
        load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        save_btn = ctk.CTkButton(
            self.setting_tab,
            text="保存修改",
            command=self.save_novel_architecture,
            font=("Microsoft YaHei", 12)
        )
        save_btn.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.setting_text = ctk.CTkTextbox(self.setting_tab, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.setting_text)
        self.setting_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

    def load_novel_architecture(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        filename = os.path.join(filepath, "Novel_architecture.txt")
        content = read_file(filename)
        self.setting_text.delete("0.0", "end")
        self.setting_text.insert("0.0", content)
        self.log("已加载 Novel_architecture.txt 内容到编辑区。")

    def save_novel_architecture(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        content = self.setting_text.get("0.0", "end").strip()
        filename = os.path.join(filepath, "Novel_architecture.txt")
        clear_file_content(filename)
        save_string_to_txt(content, filename)
        self.log("已保存对 Novel_architecture.txt 的修改。")

    # ----------------- Chapter Blueprint 标签页 -----------------
    def build_directory_tab(self):
        self.directory_tab.rowconfigure(0, weight=0)
        self.directory_tab.rowconfigure(1, weight=1)
        self.directory_tab.columnconfigure(0, weight=1)

        load_btn = ctk.CTkButton(
            self.directory_tab,
            text="加载 Novel_directory.txt",
            command=self.load_chapter_blueprint,
            font=("Microsoft YaHei", 12)
        )
        load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        save_btn = ctk.CTkButton(
            self.directory_tab,
            text="保存修改",
            command=self.save_chapter_blueprint,
            font=("Microsoft YaHei", 12)
        )
        save_btn.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.directory_text = ctk.CTkTextbox(self.directory_tab, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.directory_text)
        self.directory_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

    def load_chapter_blueprint(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        filename = os.path.join(filepath, "Novel_directory.txt")
        content = read_file(filename)
        self.directory_text.delete("0.0", "end")
        self.directory_text.insert("0.0", content)
        self.log("已加载 Novel_directory.txt 内容到编辑区。")

    def save_chapter_blueprint(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        content = self.directory_text.get("0.0", "end").strip()
        filename = os.path.join(filepath, "Novel_directory.txt")
        clear_file_content(filename)
        save_string_to_txt(content, filename)
        self.log("已保存对 Novel_directory.txt 的修改。")

    # ----------------- Character State 标签页 -----------------
    def build_character_tab(self):
        self.character_tab.rowconfigure(0, weight=0)
        self.character_tab.rowconfigure(1, weight=1)
        self.character_tab.columnconfigure(0, weight=1)

        load_btn = ctk.CTkButton(
            self.character_tab,
            text="加载 character_state.txt",
            command=self.load_character_state,
            font=("Microsoft YaHei", 12)
        )
        load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        save_btn = ctk.CTkButton(
            self.character_tab,
            text="保存修改",
            command=self.save_character_state,
            font=("Microsoft YaHei", 12)
        )
        save_btn.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.character_text = ctk.CTkTextbox(self.character_tab, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.character_text)
        self.character_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

    def load_character_state(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        filename = os.path.join(filepath, "character_state.txt")
        content = read_file(filename)
        self.character_text.delete("0.0", "end")
        self.character_text.insert("0.0", content)
        self.log("已加载 character_state.txt 到编辑区。")

    def save_character_state(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        content = self.character_text.get("0.0", "end").strip()
        filename = os.path.join(filepath, "character_state.txt")
        clear_file_content(filename)
        save_string_to_txt(content, filename)
        self.log("已保存对 character_state.txt 的修改。")

    # ----------------- Global Summary 标签页 -----------------
    def build_summary_tab(self):
        self.summary_tab.rowconfigure(0, weight=0)
        self.summary_tab.rowconfigure(1, weight=1)
        self.summary_tab.columnconfigure(0, weight=1)

        load_btn = ctk.CTkButton(
            self.summary_tab,
            text="加载 global_summary.txt",
            command=self.load_global_summary,
            font=("Microsoft YaHei", 12)
        )
        load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        save_btn = ctk.CTkButton(
            self.summary_tab,
            text="保存修改",
            command=self.save_global_summary,
            font=("Microsoft YaHei", 12)
        )
        save_btn.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.summary_text = ctk.CTkTextbox(self.summary_tab, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.summary_text)
        self.summary_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

    def load_global_summary(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        filename = os.path.join(filepath, "global_summary.txt")
        content = read_file(filename)
        self.summary_text.delete("0.0", "end")
        self.summary_text.insert("0.0", content)
        self.log("已加载 global_summary.txt 到编辑区。")

    def save_global_summary(self):
        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先设置保存文件路径")
            return
        content = self.summary_text.get("0.0", "end").strip()
        filename = os.path.join(filepath, "global_summary.txt")
        clear_file_content(filename)
        save_string_to_txt(content, filename)
        self.log("已保存对 global_summary.txt 的修改。")

    # ----------------- Chapters Manage 标签页 -----------------
    def build_chapters_tab(self):
        """
        章节浏览与管理：可选择某一章进行查看/编辑，并保存修改。
        """
        self.chapters_view_tab.rowconfigure(0, weight=0)
        self.chapters_view_tab.rowconfigure(1, weight=1)
        self.chapters_view_tab.columnconfigure(0, weight=1)

        top_frame = ctk.CTkFrame(self.chapters_view_tab)
        top_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        top_frame.columnconfigure(0, weight=0)
        top_frame.columnconfigure(1, weight=0)
        top_frame.columnconfigure(2, weight=0)
        top_frame.columnconfigure(3, weight=0)
        top_frame.columnconfigure(4, weight=1)

        prev_btn = ctk.CTkButton(top_frame, text="<< 上一章", command=self.prev_chapter, font=("Microsoft YaHei", 12))
        prev_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        next_btn = ctk.CTkButton(top_frame, text="下一章 >>", command=self.next_chapter, font=("Microsoft YaHei", 12))
        next_btn.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.chapter_select_var = ctk.StringVar(value="")

        # 下拉菜单（若章节超10个，则启用滚动限制）
        self.chapter_select_menu = ctk.CTkOptionMenu(
            top_frame,
            values=[],
            variable=self.chapter_select_var,
            command=self.on_chapter_selected,
            font=("Microsoft YaHei", 12)
        )
        self.chapter_select_menu.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        save_btn = ctk.CTkButton(top_frame, text="保存修改", command=self.save_current_chapter, font=("Microsoft YaHei", 12))
        save_btn.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        refresh_btn = ctk.CTkButton(top_frame, text="刷新章节列表", command=self.refresh_chapters_list, font=("Microsoft YaHei", 12))
        refresh_btn.grid(row=0, column=4, padx=5, pady=5, sticky="e")

        self.chapter_view_text = ctk.CTkTextbox(self.chapters_view_tab, wrap="word", font=("Microsoft YaHei", 12))
        TextWidgetContextMenu(self.chapter_view_text)
        self.chapter_view_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.chapters_list = []
        self.refresh_chapters_list()

    def refresh_chapters_list(self):
        """
        刷新并获取当前保存路径下的所有章节txt文件，并更新下拉菜单。
        当章节多于10个时，启用CTkOptionMenu的滚动限制。
        """
        filepath = self.filepath_var.get().strip()
        chapters_dir = os.path.join(filepath, "chapters")
        
        if not os.path.exists(chapters_dir):
            self.safe_log("尚未找到 chapters 文件夹，请先生成章节或检查保存路径。")
            self.chapter_select_menu.configure(values=[])
            return

        all_files = os.listdir(chapters_dir)
        chapter_nums = []
        for f in all_files:
            if f.startswith("chapter_") and f.endswith(".txt"):
                number_part = f.replace("chapter_", "").replace(".txt", "")
                if number_part.isdigit():
                    chapter_nums.append(number_part)

        chapter_nums.sort(key=lambda x: int(x))
        self.chapters_list = chapter_nums
        self.chapter_select_menu.configure(values=self.chapters_list)

        current_selected = self.chapter_select_var.get()
        if current_selected not in self.chapters_list:
            if self.chapters_list:
                self.chapter_select_var.set(self.chapters_list[0])
                self.load_chapter_content(self.chapters_list[0])
            else:
                self.chapter_select_var.set("")
                self.chapter_view_text.delete("0.0", "end")

    def on_chapter_selected(self, value):
        """
        当下拉菜单选择变化时，加载对应章节内容到文本框。
        """
        self.load_chapter_content(value)

    def load_chapter_content(self, chapter_number_str):
        if not chapter_number_str:
            return
        filepath = self.filepath_var.get().strip()
        chapter_file = os.path.join(filepath, "chapters", f"chapter_{chapter_number_str}.txt")
        if not os.path.exists(chapter_file):
            self.safe_log(f"章节文件 {chapter_file} 不存在！")
            return

        content = read_file(chapter_file)
        self.chapter_view_text.delete("0.0", "end")
        self.chapter_view_text.insert("0.0", content)

    def save_current_chapter(self):
        """
        将当前查看的章节内容保存回对应文件。
        """
        chapter_number_str = self.chapter_select_var.get()
        if not chapter_number_str:
            messagebox.showwarning("警告", "尚未选择章节，无法保存。")
            return

        filepath = self.filepath_var.get().strip()
        if not filepath:
            messagebox.showwarning("警告", "请先配置保存文件路径")
            return

        chapter_file = os.path.join(filepath, "chapters", f"chapter_{chapter_number_str}.txt")
        content = self.chapter_view_text.get("0.0", "end").strip()

        clear_file_content(chapter_file)
        save_string_to_txt(content, chapter_file)
        self.safe_log(f"已保存对第 {chapter_number_str} 章的修改。")

    def prev_chapter(self):
        """
        切换到上一章
        """
        if not self.chapters_list:
            return
        current = self.chapter_select_var.get()
        if current not in self.chapters_list:
            return
        idx = self.chapters_list.index(current)
        if idx > 0:
            new_idx = idx - 1
            self.chapter_select_var.set(self.chapters_list[new_idx])
            self.load_chapter_content(self.chapters_list[new_idx])
        else:
            messagebox.showinfo("提示", "已经是第一章了。")

    def next_chapter(self):
        """
        切换到下一章
        """
        if not self.chapters_list:
            return
        current = self.chapter_select_var.get()
        if current not in self.chapters_list:
            return
        idx = self.chapters_list.index(current)
        if idx < len(self.chapters_list) - 1:
            new_idx = idx + 1
            self.chapter_select_var.set(self.chapters_list[new_idx])
            self.load_chapter_content(self.chapters_list[new_idx])
        else:
            messagebox.showinfo("提示", "已经是最后一章了。")

    def test_llm_config(self):
        """
        测试当前的LLM配置是否可用
        """
        interface_format = self.interface_format_var.get().strip()
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        model_name = self.model_name_var.get().strip()
        temperature = self.temperature_var.get()
        max_tokens = self.max_tokens_var.get()
        timeout = self.timeout_var.get()

        test_llm_config(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            log_func=self.safe_log,
            handle_exception_func=self.handle_exception
        )

    def test_embedding_config(self):
        """
        测试当前的Embedding配置是否可用
        """
        api_key = self.embedding_api_key_var.get().strip()
        base_url = self.embedding_url_var.get().strip()
        interface_format = self.embedding_interface_format_var.get().strip()
        model_name = self.embedding_model_name_var.get().strip()

        test_embedding_config(
            api_key=api_key,
            base_url=base_url,
            interface_format=interface_format,
            model_name=model_name,
            log_func=self.safe_log,
            handle_exception_func=self.handle_exception
        )

    def count_chinese_and_english(self, text):
        """
        计算文本中的中文字符和英文单词数量
        """
        # 计算中文字符
        chinese_count = len([char for char in text if '\u4e00' <= char <= '\u9fff'])
        
        # 计算英文单词
        english_words = re.findall(r'\b[a-zA-Z]+\b', text)
        english_word_count = len(english_words)

        # 返回中文字符和英文单词的总数
        return chinese_count + english_word_count

# ----------------- 程序入口 -----------------
if __name__ == "__main__":
    app = ctk.CTk()
    gui = NovelGeneratorGUI(app)
    app.mainloop()
