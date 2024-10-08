"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import omni.kit.usd_undo
import omni.kit.window.popup_dialog.message_dialog
import omni.usd
import pxr.Tf
import pxr.Usd

prim_filter_setting_path = "/exts/lightspeed.lock_xform/prim_filter"


class LockXformSession:
    """A "session" (associated with a stage). Keeps track of an individual stage's prims + disabling the lock"""

    def __init__(self, identifier, stage, display_dialog_callback):
        self._enabled = True
        self._id = identifier  # id isn't really used, but leaving it here for debug and convenience
        self._prim_xformOp_cache = set()
        # Register USD Notifer/Listener whenever UsdObjects are changed
        self._listener = pxr.Tf.Notice.RegisterGlobally(pxr.Usd.Notice.ObjectsChanged, self._undo_xform_deltas)
        self._usd_undo = omni.kit.usd_undo.UsdEditTargetUndo(stage.GetEditTarget())
        self._display_dialog = True
        self._display_dialog_callback = display_dialog_callback

    def set_enablement(self, enabled):
        self._enabled = enabled

    def lock_prims(self, stage, prim_paths):
        """A "session" (associated with a stage). Keeps track of an individual stage's prims + disabling the lock"""
        # Reset prim cache
        self._prim_xformOp_cache = set()
        for prim_path in prim_paths:
            prim = stage.GetPrimAtPath(prim_path)
            for attr in prim.GetAttributes():
                attr_path = attr.GetPath()
                if "xformOp:" in str(attr_path):
                    # Cache prim state using usd_undo module
                    self._usd_undo.reserve(attr_path)
                    self._prim_xformOp_cache.add(attr_path)

    def _undo_xform_deltas(self, usd_notice, stage):
        if self._enabled:
            _undo_occurred = False
            # Only care about prims that have actually changed; not their subtrees
            attr_paths_changed = usd_notice.GetChangedInfoOnlyPaths()
            for attr_path in attr_paths_changed:
                if attr_path in self._prim_xformOp_cache:
                    # Undo prim change
                    self._usd_undo.undo()
                    _undo_occurred = True
            if self._display_dialog and _undo_occurred:
                # Display dialog only once
                self._display_dialog = False
                self._display_dialog_callback()
