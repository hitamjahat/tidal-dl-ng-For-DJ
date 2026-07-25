from PySide6.QtWidgets import QDialog, QLabel, QPushButton

class Ui_DialogVersion:
    def setupUi(self, dialog: QDialog) -> None: ...
    def retranslateUi(self, dialog: QDialog) -> None: ...
    l_version: QLabel
    l_error: QLabel
    l_error_details: QLabel
    l_h_version: QLabel
    l_h_version_new: QLabel
    l_version_new: QLabel
    l_changelog: QLabel
    l_changelog_details: QLabel
    l_name_app: QLabel
    l_url_github: QLabel
    pb_download: QPushButton
