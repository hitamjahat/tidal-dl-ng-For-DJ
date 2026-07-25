from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser

class Ui_DialogLogin:
    def setupUi(self, dialog: QDialog) -> None: ...
    def retranslateUi(self, dialog: QDialog) -> None: ...
    tb_url_login: QTextBrowser
    l_hint: QLabel
    l_expires_date_time: QLabel
    l_description: QLabel
    l_expires_description: QLabel
    l_header: QLabel
    bb_dialog: QDialogButtonBox
