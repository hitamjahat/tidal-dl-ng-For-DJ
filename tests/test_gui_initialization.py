"""Regression tests for responsive main-window initialization."""

from __future__ import annotations

import os
import unittest
from typing import ClassVar, cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.media import Quality

from tidal_dl_ng.config import Settings
from tidal_dl_ng.gui.initialization import (
    DEFAULT_SEARCH_TYPE_INDEX,
    DUPLICATE_ACTION_NAME,
    RESULT_COLUMN_LABELS,
    VIEW_HISTORY_ACTION_NAME,
    InitializationMixin,
)
from tidal_dl_ng.history import HistoryService, SettingsData
from tidal_dl_ng.model.cfg import Settings as ModelSettings


class _ModelSettingsFixture:
    """Provide the model settings used by initialization tests."""

    skip_existing: bool = False
    download_base_path: str = "~/download"
    window_x: int = 50
    window_y: int = 50
    window_w: int = 1200
    window_h: int = 800


class _SettingsFixture:
    """Provide in-memory application settings without filesystem access."""

    def __init__(self) -> None:
        """Create default model settings."""
        self.data = cast("ModelSettings", _ModelSettingsFixture())


class _HistoryServiceFixture:
    """Provide duplicate-prevention settings for menu initialization."""

    def get_settings(self) -> SettingsData:
        """Return enabled duplicate prevention.

        Returns:
            SettingsData: History-related test settings.
        """
        return {"preventDuplicates": True}


class _InitializationHost(QtWidgets.QMainWindow, InitializationMixin):
    """Supply concrete Qt signals and callbacks to the initialization mixin."""

    s_item_advance = QtCore.Signal(float)
    s_item_name = QtCore.Signal(str)
    s_list_advance = QtCore.Signal(float)
    s_list_name = QtCore.Signal(str)

    def __init__(self) -> None:
        """Create a minimal main-window host for focused tests."""
        super().__init__()
        self.settings = cast("Settings", _SettingsFixture())
        self.history_service = cast(
            "HistoryService",
            _HistoryServiceFixture(),
        )
        self.statusbar = self.statusBar()
        self.l_pm_cover = QtWidgets.QLabel(self)
        self.cb_search_type = QtWidgets.QComboBox(self)

    def handle_filter_activated(self) -> None:
        """Handle a test filter activation."""

    def menu_context_tree_results(self, point: QtCore.QPoint) -> None:
        """Handle a test results context-menu request.

        Args:
            point (QPoint): Requested menu position.
        """

    def menu_context_queue_download(self, point: QtCore.QPoint) -> None:
        """Handle a test queue context-menu request.

        Args:
            point (QPoint): Requested menu position.
        """

    def on_track_hover_confirmed(self, media: object) -> None:
        """Handle a test hover confirmation.

        Args:
            media (object): Hovered media payload.
        """

    def on_track_hover_left(self) -> None:
        """Handle a test hover exit."""

    def on_view_history(self) -> None:
        """Handle a test history action."""

    def on_toggle_duplicate_prevention(self, enabled: bool) -> None:
        """Handle a test duplicate-prevention toggle.

        Args:
            enabled (bool): New duplicate-prevention state.
        """

    def initialize_results(
        self,
        tree: QtWidgets.QTreeView,
        model: QtGui.QStandardItemModel,
    ) -> None:
        """Expose results initialization through the concrete test host.

        Args:
            tree (QTreeView): Results view to initialize.
            model (QStandardItemModel): Source model to initialize.
        """
        self._init_tree_results_model(model)
        self._init_tree_results(tree, model)

    def populate_quality_options(
        self,
        combo_box: QtWidgets.QComboBox,
        options: object,
    ) -> None:
        """Expose quality population through the concrete test host.

        Args:
            combo_box (QComboBox): Target combo box.
            options (object): Runtime enum options.
        """
        self._populate_quality(combo_box, options)

    def populate_search_options(
        self,
        combo_box: QtWidgets.QComboBox,
        options: object,
    ) -> None:
        """Expose search-type population through the concrete test host.

        Args:
            combo_box (QComboBox): Target combo box.
            options (object): Runtime media classes.
        """
        self._populate_search_types(combo_box, options)


class TestInitializationMixin(unittest.TestCase):
    """Verify responsive initialization behavior with real Qt models."""

    application: ClassVar[QtWidgets.QApplication]

    @classmethod
    def setUpClass(cls) -> None:
        """Create one offscreen Qt application for this test class."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        existing = QtWidgets.QApplication.instance()
        cls.application = (
            existing
            if isinstance(existing, QtWidgets.QApplication)
            else QtWidgets.QApplication([])
        )

    def setUp(self) -> None:
        """Create a fresh minimal main window."""
        self.host = _InitializationHost()

    def tearDown(self) -> None:
        """Destroy the test window after each case."""
        self.host.close()
        self.host.deleteLater()
        self.application.processEvents()

    def test_initialize_gui_clamps_geometry_to_screen(self) -> None:
        """Invalid saved geometry should remain inside the active screen."""
        settings_data = self.host.settings.data
        settings_data.window_x = -50_000
        settings_data.window_y = 50_000
        settings_data.window_w = 50_000
        settings_data.window_h = -1

        self.host.initialize_gui()

        available = self.host.screen().availableGeometry()
        self.assertTrue(available.contains(self.host.geometry()))
        self.assertGreater(self.host.width(), 0)
        self.assertGreater(self.host.height(), 0)

    def test_results_view_uses_proxy_and_responsive_header(self) -> None:
        """Results initialization should install model/view infrastructure."""
        tree = QtWidgets.QTreeView(self.host)
        model = QtGui.QStandardItemModel(self.host)

        self.host.initialize_results(tree, model)

        self.assertIs(tree.model(), self.host.proxy_tr_results)
        self.assertIs(self.host.proxy_tr_results.sourceModel(), model)
        self.assertEqual(model.columnCount(), len(RESULT_COLUMN_LABELS))
        self.assertTrue(tree.isColumnHidden(1))
        self.assertTrue(tree.uniformRowHeights())

    def test_combo_population_is_idempotent_and_selects_track(self) -> None:
        """Repeated population should replace rather than duplicate options."""
        quality_combo = QtWidgets.QComboBox(self.host)
        self.host.populate_quality_options(quality_combo, Quality)
        initial_quality_count = quality_combo.count()
        self.host.populate_quality_options(quality_combo, Quality)

        self.assertGreater(initial_quality_count, 0)
        self.assertEqual(quality_combo.count(), initial_quality_count)

        search_combo = QtWidgets.QComboBox(self.host)
        search_types: list[type[object] | None] = [dict, list, str, None]
        self.host.populate_search_options(search_combo, search_types)

        self.assertEqual(search_combo.count(), 3)
        self.assertEqual(
            search_combo.currentIndex(), DEFAULT_SEARCH_TYPE_INDEX
        )
        self.assertIs(search_combo.currentData(), str)

    def test_menu_actions_are_accessible_and_restore_history_state(
        self,
    ) -> None:
        """History actions should expose stable names and restored state."""
        self.host.initialize_menu_actions()

        self.assertEqual(
            self.host.a_view_history.objectName(),
            VIEW_HISTORY_ACTION_NAME,
        )
        self.assertEqual(
            self.host.a_toggle_duplicate_prevention.objectName(),
            DUPLICATE_ACTION_NAME,
        )
        self.assertTrue(self.host.a_toggle_duplicate_prevention.isChecked())
        self.assertFalse(self.host.a_view_history.shortcut().isEmpty())
