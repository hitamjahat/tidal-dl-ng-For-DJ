"""Stub for generated Ui_DialogSettings."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QStackedWidget,
)

class Ui_DialogSettings:
    """UI for settings dialog."""

    def setupUi(self, dialog: QDialog) -> None: ...
    def retranslateUi(self, dialog: QDialog) -> None: ...
    lw_categories: QListWidget
    sw_categories: QStackedWidget
    le_download_base_path: QLineEdit
    le_path_binary_ffmpeg: QLineEdit
    pb_download_base_path: QPushButton
    pb_path_binary_ffmpeg: QPushButton
    le_format_album: QLineEdit
    le_format_playlist: QLineEdit
    le_format_mix: QLineEdit
    le_format_track: QLineEdit
    le_format_video: QLineEdit
    le_metadata_delimiter_artist: QLineEdit
    le_metadata_delimiter_album_artist: QLineEdit
    le_filename_delimiter_artist: QLineEdit
    le_filename_delimiter_album_artist: QLineEdit
    sb_album_track_num_pad_min: QSpinBox
    sb_downloads_concurrent_max: QSpinBox
    c_quality_audio: QComboBox
    c_quality_video: QComboBox
    c_metadata_cover_dimension: QComboBox
    cb_lyrics_embed: QCheckBox
    cb_lyrics_file: QCheckBox
    cb_use_primary_album_artist: QCheckBox
    cb_video_download: QCheckBox
    cb_download_dolby_atmos: QCheckBox
    cb_download_delay: QCheckBox
    cb_video_convert_mp4: QCheckBox
    cb_extract_flac: QCheckBox
    cb_metadata_cover_embed: QCheckBox
    cb_mark_explicit: QCheckBox
    cb_cover_album_file: QCheckBox
    cb_skip_existing: QCheckBox
    cb_symlink_to_track: QCheckBox
    cb_playlist_create: QCheckBox
    l_quality_audio: QLabel
    l_quality_video: QLabel
    l_metadata_cover_dimension: QLabel
    l_download_base_path: QLabel
    l_format_album: QLabel
    l_format_playlist: QLabel
    l_format_mix: QLabel
    l_format_track: QLabel
    l_format_video: QLabel
    l_path_binary_ffmpeg: QLabel
    l_metadata_delimiter_artist: QLabel
    l_metadata_delimiter_album_artist: QLabel
    l_filename_delimiter_artist: QLabel
    l_filename_delimiter_album_artist: QLabel
    l_album_track_num_pad_min: QLabel
    l_downloads_concurrent_max: QLabel
    l_icon_quality_audio: QLabel
    l_icon_quality_video: QLabel
    l_icon_metadata_cover_dimension: QLabel
    l_icon_download_base_path: QLabel
    l_icon_format_album: QLabel
    l_icon_format_playlist: QLabel
    l_icon_format_mix: QLabel
    l_icon_format_track: QLabel
    l_icon_format_video: QLabel
    l_icon_path_binary_ffmpeg: QLabel
    l_icon_metadata_delimiter_artist: QLabel
    l_icon_metadata_delimiter_album_artist: QLabel
    l_icon_filename_delimiter_artist: QLabel
    l_icon_filename_delimiter_album_artist: QLabel
    l_icon_album_track_num_pad_min: QLabel
    l_icon_downloads_concurrent_max: QLabel
    lw_categories: QListWidget
    sw_categories: QStackedWidget
    le_download_base_path: QLineEdit
    le_path_binary_ffmpeg: QLineEdit
    pb_download_base_path: QPushButton
    pb_path_binary_ffmpeg: QPushButton
