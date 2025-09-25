import sys
import os
import json
import re
import math
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QTabWidget, QMessageBox, QProgressDialog,
    QMenuBar, QAction, QFrame, QListWidget, QListWidgetItem, QComboBox, QSlider,
    QStyle, QTimeEdit, QLineEdit, QStackedWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QSettings, QUrl, QTime
from PyQt5.QtGui import QIcon, QIntValidator
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# Cấu hình
APP_NAME = "MerCut Pro"
APP_VERSION = "3.3.0" # Cập nhật phiên bản
ORGANIZATION_NAME = "Gemini AI"
SETTINGS_KEY_LANGUAGE = "language"

# Lớp LanguageManager (không thay đổi)
class LanguageManager(QObject):
    languageChanged = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self.translations = {}
        self.load_language()
    def load_language(self, lang_code=None):
        if lang_code is None: lang_code = self.settings.value(SETTINGS_KEY_LANGUAGE, "vi", type=str)
        file_path = f'lang/lang_{lang_code}.json'
        try:
            with open(file_path, 'r', encoding='utf-8') as f: self.translations = json.load(f)
            self.settings.setValue(SETTINGS_KEY_LANGUAGE, lang_code)
            self.languageChanged.emit()
        except FileNotFoundError:
            QMessageBox.critical(None, "Language File Error", f"Cannot find '{file_path}'.")
            if lang_code != "en": self.load_language("en")
    def get(self, key: str) -> str: return self.translations.get(key, key)

# Lớp VideoProcessor (không thay đổi)
class VideoProcessor(QObject):
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_cancelled = False
        from moviepy.editor import VideoFileClip, concatenate_videoclips
        self.VideoFileClip = VideoFileClip
        self.concatenate_videoclips = concatenate_videoclips

    def get_quality_preset(self, quality_str):
        return {"Thấp": "1000k", "Trung bình": "5000k", "Cao": "10000k",
                "Low": "1000k", "Medium": "5000k", "High": "10000k"}.get(quality_str, "5000k")

    def cut_video_by_range(self, file_path: str, start_time: int, end_time: int, output_path: str, quality: str):
        try:
            self.is_cancelled = False
            bitrate = self.get_quality_preset(quality)
            with self.VideoFileClip(file_path) as video:
                if self.is_cancelled: return
                clip = video.subclip(start_time, end_time)
                clip.write_videofile(output_path, codec="libx264", audio_codec="aac", bitrate=bitrate, logger=None)
            if not self.is_cancelled: self.finished.emit("cut", output_path)
        except Exception as e: self.error.emit(f"Lỗi khi cắt video: {e}")

    def split_video_by_duration(self, file_path: str, duration_sec: int, output_dir: str, quality: str):
        try:
            self.is_cancelled = False
            bitrate = self.get_quality_preset(quality)
            with self.VideoFileClip(file_path) as video:
                total_duration = video.duration
                num_clips = math.ceil(total_duration / duration_sec)
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                for i in range(num_clips):
                    if self.is_cancelled: break
                    start_time = i * duration_sec
                    end_time = min((i + 1) * duration_sec, total_duration)
                    if start_time >= end_time: continue
                    output_filename = os.path.join(output_dir, f"{base_name}_part_{i+1}.mp4")
                    clip = video.subclip(start_time, end_time)
                    clip.write_videofile(output_filename, codec="libx264", audio_codec="aac", bitrate=bitrate, logger=None)
                    self.progress.emit(int(((i + 1) / num_clips) * 100))
            if not self.is_cancelled: self.finished.emit("split", output_dir)
        except Exception as e: self.error.emit(f"Lỗi khi chia video: {e}")

    def merge_videos(self, file_paths: list, output_path: str, quality: str):
        try:
            self.is_cancelled = False
            bitrate = self.get_quality_preset(quality)
            clips = [self.VideoFileClip(path) for path in file_paths]
            if self.is_cancelled:
                for clip in clips: clip.close()
                return
            final_clip = self.concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", bitrate=bitrate, logger=None)
            for clip in clips: clip.close()
            final_clip.close()
            if not self.is_cancelled: self.finished.emit("merge", output_path)
        except Exception as e: self.error.emit(f"Lỗi khi ghép video: {e}")

    def cancel(self): self.is_cancelled = True

# Lớp Giao diện chính
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from moviepy.editor import VideoFileClip
        self.VideoFileClip = VideoFileClip
        self.setAcceptDrops(True)
        self.lang_manager = LanguageManager(self)
        self.worker_thread = None
        self.current_video_path = None
        self.init_ui()
        self.lang_manager.languageChanged.connect(self.retranslate_ui)

    def init_ui(self):
        self.setWindowTitle(self.lang_manager.get("app_title"))
        self.setGeometry(100, 100, 850, 600)
        self.create_menu()
        self.tabs = QTabWidget()
        self.cut_tab = self.create_cut_tab()
        self.merge_tab = self.create_merge_tab()
        self.tabs.addTab(self.cut_tab, "")
        self.tabs.addTab(self.merge_tab, "")
        self.setCentralWidget(self.tabs)
        self.apply_styles()
        self.retranslate_ui()
        
    def create_menu(self):
        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        self.menu_language = self.menu_bar.addMenu("")
        action_vi = QAction("Tiếng Việt", self, triggered=lambda: self.lang_manager.load_language("vi"))
        self.menu_language.addAction(action_vi)
        action_en = QAction("English", self, triggered=lambda: self.lang_manager.load_language("en"))
        self.menu_language.addAction(action_en)
        self.menu_about = self.menu_bar.addMenu("")
        self.action_show_about = QAction("", self, triggered=self.show_about_dialog)
        self.menu_about.addAction(self.action_show_about)

    def create_cut_tab(self):
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        
        left_layout = QVBoxLayout()
        self.video_widget = QVideoWidget()
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.media_player.setVideoOutput(self.video_widget)
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.sliderMoved.connect(self.set_media_position)
        self.media_player.positionChanged.connect(self.media_position_changed)
        self.media_player.durationChanged.connect(self.media_duration_changed)

        player_controls = QHBoxLayout()
        self.play_button = QPushButton(icon=self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_play)
        self.current_time_label = QLabel("00:00:00")
        self.total_time_label = QLabel("00:00:00")
        player_controls.addWidget(self.play_button)
        player_controls.addWidget(self.current_time_label)
        player_controls.addWidget(self.time_slider)
        player_controls.addWidget(self.total_time_label)
        left_layout.addWidget(self.video_widget, 5)
        left_layout.addLayout(player_controls)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)
        self.btn_browse_cut = QPushButton(clicked=self.select_video_to_cut)
        
        self.info_group = QFrame(objectName="settingsGroup")
        info_layout = QVBoxLayout(self.info_group)
        self.info_title = QLabel()
        self.duration_label = QLabel()
        self.resolution_label = QLabel()
        info_layout.addWidget(self.info_title)
        info_layout.addWidget(self.duration_label)
        info_layout.addWidget(self.resolution_label)

        settings_group = QFrame(objectName="settingsGroup")
        settings_layout = QVBoxLayout(settings_group)
        self.settings_title = QLabel()
        
        cut_mode_layout = QHBoxLayout()
        self.cut_mode_label = QLabel()
        self.cut_mode_combo = QComboBox()
        self.cut_mode_combo.currentIndexChanged.connect(self.on_cut_mode_changed)
        cut_mode_layout.addWidget(self.cut_mode_label)
        cut_mode_layout.addWidget(self.cut_mode_combo)
        
        self.cut_options_stack = QStackedWidget()
        self.range_cut_widget = self.create_range_cut_widget()
        self.duration_cut_widget = self.create_duration_cut_widget()
        self.cut_options_stack.addWidget(self.range_cut_widget)
        self.cut_options_stack.addWidget(self.duration_cut_widget)
        
        quality_layout = QHBoxLayout()
        self.quality_label = QLabel()
        self.quality_combo = QComboBox()
        quality_layout.addWidget(self.quality_label)
        quality_layout.addWidget(self.quality_combo)
        
        settings_layout.addWidget(self.settings_title)
        settings_layout.addLayout(cut_mode_layout)
        settings_layout.addWidget(self.cut_options_stack)
        settings_layout.addLayout(quality_layout)

        self.btn_start_cut = QPushButton(objectName="executeButton", clicked=self.start_cutting_process)
        right_layout.addWidget(self.btn_browse_cut)
        right_layout.addWidget(self.info_group)
        right_layout.addWidget(settings_group)
        right_layout.addStretch()
        right_layout.addWidget(self.btn_start_cut)

        main_layout.addLayout(left_layout, 7)
        main_layout.addLayout(right_layout, 3)
        return widget

    def create_range_cut_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        start_layout = QHBoxLayout()
        self.start_time_label = QLabel()
        self.start_time_edit = QTimeEdit(displayFormat="HH:mm:ss")
        start_layout.addWidget(self.start_time_label)
        start_layout.addWidget(self.start_time_edit)
        
        end_layout = QHBoxLayout()
        self.end_time_label = QLabel()
        self.end_time_edit = QTimeEdit(displayFormat="HH:mm:ss")
        end_layout.addWidget(self.end_time_label)
        end_layout.addWidget(self.end_time_edit)
        layout.addLayout(start_layout)
        layout.addLayout(end_layout)
        return widget

    def create_duration_cut_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        self.duration_part_label = QLabel()
        self.duration_part_edit = QLineEdit()
        self.duration_part_edit.setValidator(QIntValidator(1, 99999))
        self.duration_part_edit.setPlaceholderText("e.g., 60")
        layout.addWidget(self.duration_part_label)
        layout.addWidget(self.duration_part_edit)
        return widget
    
    def on_cut_mode_changed(self, index):
        self.cut_options_stack.setCurrentIndex(index)
        
    def create_merge_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        self.merge_list_label = QLabel()
        self.merge_list_widget = QListWidget(dragDropMode=QListWidget.InternalMove, alternatingRowColors=True)
        controls_layout = QHBoxLayout()
        self.btn_add_merge = QPushButton(icon=self.style().standardIcon(QStyle.SP_FileDialogNewFolder), clicked=self.select_videos_to_merge)
        self.btn_remove_merge = QPushButton(icon=self.style().standardIcon(QStyle.SP_TrashIcon), clicked=self.remove_selected_from_merge)
        self.btn_move_up = QPushButton(icon=self.style().standardIcon(QStyle.SP_ArrowUp), clicked=self.move_merge_item_up)
        self.btn_move_down = QPushButton(icon=self.style().standardIcon(QStyle.SP_ArrowDown), clicked=self.move_merge_item_down)
        self.btn_clear_merge = QPushButton(icon=self.style().standardIcon(QStyle.SP_DialogResetButton), clicked=self.merge_list_widget.clear)
        controls_layout.addWidget(self.btn_add_merge)
        controls_layout.addWidget(self.btn_remove_merge)
        controls_layout.addWidget(self.btn_move_up)
        controls_layout.addWidget(self.btn_move_down)
        controls_layout.addStretch()
        controls_layout.addWidget(self.btn_clear_merge)
        bottom_layout = QHBoxLayout()
        quality_merge_layout = QHBoxLayout()
        self.quality_label_merge = QLabel()
        self.quality_combo_merge = QComboBox()
        quality_merge_layout.addWidget(self.quality_label_merge)
        quality_merge_layout.addWidget(self.quality_combo_merge)
        self.btn_start_merge = QPushButton(objectName="executeButton", clicked=self.start_merging_process)
        bottom_layout.addLayout(quality_merge_layout)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_start_merge)
        main_layout.addWidget(self.merge_list_label)
        main_layout.addWidget(self.merge_list_widget)
        main_layout.addLayout(controls_layout)
        main_layout.addLayout(bottom_layout)
        return widget

    def start_cutting_process(self):
        if not self.current_video_path:
            QMessageBox.warning(self, self.lang_manager.get("error_title"), self.lang_manager.get("file_not_selected_error"))
            return

        mode_index = self.cut_mode_combo.currentIndex()
        quality = self.quality_combo.currentText()

        if mode_index == 0:
            start_sec = QTime(0,0).secsTo(self.start_time_edit.time())
            end_sec = QTime(0,0).secsTo(self.end_time_edit.time())
            if start_sec >= end_sec:
                QMessageBox.warning(self, self.lang_manager.get("error_title"), self.lang_manager.get("start_time_error"))
                return
            output_path, _ = QFileDialog.getSaveFileName(self, self.lang_manager.get("select_output_file_cut"), f"{os.path.basename(self.current_video_path)}_cut.mp4", "MP4 Files (*.mp4)")
            if output_path:
                self.run_video_task('cut_range', file_path=self.current_video_path, start_time=start_sec, end_time=end_sec, output_path=output_path, quality=quality)
        else:
            duration_str = self.duration_part_edit.text()
            if not duration_str.isdigit() or int(duration_str) <= 0:
                QMessageBox.warning(self, self.lang_manager.get("error_title"), self.lang_manager.get("invalid_duration_error"))
                return
            duration_sec = int(duration_str)
            output_dir = QFileDialog.getExistingDirectory(self, self.lang_manager.get("select_output_folder"))
            if output_dir:
                self.run_video_task('split_duration', file_path=self.current_video_path, duration_sec=duration_sec, output_dir=output_dir, quality=quality)

    def run_video_task(self, task_type, **kwargs):
        self.progress_dialog = QProgressDialog(self.lang_manager.get("processing"), self.lang_manager.get("cancel"), 0, 100, self)
        if task_type == 'cut_range' or task_type == 'merge':
             self.progress_dialog.setMaximum(0)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.worker_thread = QThread()
        video_processor = VideoProcessor()
        video_processor.moveToThread(self.worker_thread)
        
        self.progress_dialog.canceled.connect(video_processor.cancel)
        video_processor.progress.connect(self.progress_dialog.setValue)
        video_processor.finished.connect(self.on_processing_finished)
        video_processor.error.connect(self.on_processing_error)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        task_map = {
            'cut_range': video_processor.cut_video_by_range,
            'split_duration': video_processor.split_video_by_duration,
            'merge': video_processor.merge_videos
        }
        self.worker_thread.started.connect(lambda: task_map[task_type](**kwargs))
        self.worker_thread.start()

    def on_processing_finished(self, op_type, path):
        if self.progress_dialog: self.progress_dialog.close()
        if self.worker_thread: self.worker_thread.quit()
        msg_key = f"{op_type}_success_message"
        msg = self.lang_manager.get(msg_key).format(path)
        QMessageBox.information(self, self.lang_manager.get("success_title"), msg)

    def select_videos_to_merge(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.lang_manager.get("add_files"), "", "Video Files (*.mp4 *.avi *.mov *.mkv)")
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            self.merge_list_widget.addItem(item)

    def select_video_to_cut(self):
        path, _ = QFileDialog.getOpenFileName(self, self.lang_manager.get("browse"), "", "Video Files (*.mp4 *.avi *.mov *.mkv)")
        if path:
            self.current_video_path = path
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.play_button.setEnabled(True)
            self.update_video_info(path)

    def update_video_info(self, path):
        try:
            with self.VideoFileClip(path) as clip:
                duration = clip.duration; width, height = clip.size
            self.duration_label.setText(f"{self.lang_manager.get('duration')} {QTime(0, 0).addSecs(int(duration)).toString('HH:mm:ss')}")
            self.resolution_label.setText(f"{self.lang_manager.get('resolution')} {width}x{height}")
            self.end_time_edit.setTime(QTime(0,0).addSecs(int(duration)))
        except Exception as e:
            self.duration_label.setText(f"{self.lang_manager.get('duration')} N/A")
            self.resolution_label.setText(f"{self.lang_manager.get('resolution')} N/A")
            QMessageBox.critical(self, self.lang_manager.get("error_title"), f"Could not read video info:\n{e}")

    def toggle_play(self):
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.media_player.pause(); self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.media_player.play(); self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def set_media_position(self, position): self.media_player.setPosition(position)

    def media_position_changed(self, position):
        self.time_slider.setValue(position)
        self.current_time_label.setText(QTime(0,0).addMSecs(position).toString("HH:mm:ss"))

    def media_duration_changed(self, duration):
        self.time_slider.setRange(0, duration)
        self.total_time_label.setText(QTime(0,0).addMSecs(duration).toString("HH:mm:ss"))

    def remove_selected_from_merge(self):
        for item in self.merge_list_widget.selectedItems(): self.merge_list_widget.takeItem(self.merge_list_widget.row(item))

    def move_merge_item_up(self):
        row = self.merge_list_widget.currentRow()
        if row > 0:
            item = self.merge_list_widget.takeItem(row)
            self.merge_list_widget.insertItem(row - 1, item)
            self.merge_list_widget.setCurrentRow(row - 1)

    def move_merge_item_down(self):
        row = self.merge_list_widget.currentRow()
        if row < self.merge_list_widget.count() - 1:
            item = self.merge_list_widget.takeItem(row)
            self.merge_list_widget.insertItem(row + 1, item)
            self.merge_list_widget.setCurrentRow(row + 1)

    def start_merging_process(self):
        paths = [self.merge_list_widget.item(i).data(Qt.UserRole) for i in range(self.merge_list_widget.count())]
        if len(paths) < 2:
            QMessageBox.warning(self, self.lang_manager.get("error_title"), self.lang_manager.get("merge_list_empty_error"))
            return
        output_path, _ = QFileDialog.getSaveFileName(self, self.lang_manager.get("select_output_file_merge"), "merged_video.mp4", "MP4 Files (*.mp4)")
        if output_path:
            self.run_video_task('merge', file_paths=paths, output_path=output_path, quality=self.quality_combo_merge.currentText())

    def on_processing_error(self, error_message):
        if hasattr(self, 'progress_dialog') and self.progress_dialog: self.progress_dialog.close()
        if self.worker_thread: self.worker_thread.quit()
        QMessageBox.critical(self, self.lang_manager.get("error_title"), error_message)

    def retranslate_ui(self):
        lm = self.lang_manager
        self.setWindowTitle(lm.get("app_title"))
        self.tabs.setTabText(0, lm.get("tab_cut"))
        self.tabs.setTabText(1, lm.get("tab_merge"))
        self.menu_language.setTitle(lm.get("menu_language"))
        self.menu_about.setTitle(lm.get("menu_about"))
        self.action_show_about.setText(lm.get("about_title"))
        self.btn_browse_cut.setText(f"📂 {lm.get('browse')}")
        self.info_title.setText(lm.get("video_information"))
        self.settings_title.setText(lm.get("cut_settings"))
        self.start_time_label.setText(lm.get("start_time"))
        self.end_time_label.setText(lm.get("end_time"))
        self.quality_label.setText(lm.get("quality"))
        self.btn_start_cut.setText(lm.get("start_cut"))
        qualities = [lm.get("quality_low"), lm.get("quality_medium"), lm.get("quality_high")]
        self.quality_combo.clear(); self.quality_combo.addItems(qualities); self.quality_combo.setCurrentIndex(1)
        self.cut_mode_label.setText(lm.get("cut_mode"))
        self.cut_mode_combo.clear(); self.cut_mode_combo.addItems([lm.get("cut_by_range"), lm.get("split_by_duration")])
        self.duration_part_label.setText(lm.get("duration_per_part_sec"))
        self.merge_list_label.setText(lm.get("merge_list"))
        self.btn_add_merge.setText(lm.get("add_files"))
        self.btn_remove_merge.setText(lm.get("remove_selected"))
        self.btn_move_up.setText(lm.get("move_up"))
        self.btn_move_down.setText(lm.get("move_down"))
        self.btn_clear_merge.setText(lm.get("clear_list"))
        self.quality_label_merge.setText(lm.get("quality"))
        self.quality_combo_merge.clear(); self.quality_combo_merge.addItems(qualities); self.quality_combo_merge.setCurrentIndex(1)
        self.btn_start_merge.setText(lm.get("start_merge"))

    def show_about_dialog(self): QMessageBox.information(self, self.lang_manager.get("about_title"), self.lang_manager.get("about_text"))

    def apply_styles(self):
        # CẬP NHẬT GIAO DIỆN SÁNG (LIGHT THEME)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #eaf6ff, stop: 1 #ffffff);
                color: #1c1c1c; /* Chữ màu đen */
                font-family: Segoe UI;
            }
            QTabWidget::pane {
                border: 1px solid #c5dbeA;
            }
            QTabBar::tab {
                background: #d4e5f5;
                color: #333333;
                padding: 10px 20px;
                border: 1px solid #c5dbeA;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #000000;
                font-weight: bold;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #0069d9;
            }
            QPushButton:pressed {
                background-color: #0056b3;
            }
            QPushButton#executeButton {
                background-color: #28a745;
            }
            QPushButton#executeButton:hover {
                background-color: #218838;
            }
            QFrame#settingsGroup {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #c5dbeA;
            }
            QLabel {
                font-size: 14px;
                padding: 5px;
                background-color: transparent; /* Nền trong suốt cho QLabel */
            }
            QTimeEdit, QComboBox, QLineEdit {
                background-color: #ffffff;
                color: #1c1c1c;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QVideoWidget {
                background-color: black;
            }
            QMenuBar {
                background-color: #e3f2fd;
                color: #1c1c1c;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #ced4da;
            }
            QMenu::item:selected {
                background-color: #007bff;
                color: white;
            }
        """)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        from moviepy.editor import VideoFileClip, concatenate_videoclips
    except ImportError:
        QMessageBox.critical(None, "Lỗi Thư viện", "Thư viện 'moviepy' chưa được cài đặt.\nVui lòng cài đặt bằng lệnh: pip install moviepy")
        sys.exit(1)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())