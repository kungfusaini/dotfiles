"""Human-only recovery consent on the workspace where Browser-open was invoked.

Called with the browser lock held. Reuse the existing bounded launch rule to
place only this unique GTK application, suppressing initial focus/activation.
No browser content is read and no confirmation is persisted.
"""
import os
import re
import time
import uuid

from agent_browser import placement_rule


def confirm_recovery(api, project, missing, *, workspace=None):
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, GLib

    workspace = workspace or api.active_workspace_name()
    if not workspace or any(c in workspace for c in ';[],\r\n\0'):
        raise RuntimeError('Cannot safely place browser recovery confirmation')
    app_id = 'org.projectobject.Recovery' + uuid.uuid4().hex
    application = Adw.Application(application_id=app_id)
    application.register(None)
    dialog = Adw.MessageDialog.new(None, 'Restore saved browser windows?',
        f'{project["name"]} has {missing} saved browser window(s) not currently open.\n\n'
        'Vivaldi may still be restoring its previous session. Restoring now could '
        'create duplicate windows if Vivaldi recovers them later.\n\n'
        'Restore only the missing saved windows? Existing windows and saved backups '
        'will be kept. Cancel leaves the saved session untouched.')
    application.add_window(dialog)
    dialog.add_response('cancel', 'Cancel')
    dialog.add_response('restore', 'Restore saved windows')
    dialog.set_response_appearance('restore', Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response('cancel')
    dialog.set_close_response('cancel')
    dialog.set_response_enabled('restore', False)
    loop = GLib.MainLoop()
    result = False
    failure = None
    verified = False
    deadline = time.monotonic() + 5

    def responded(_dialog, response):
        nonlocal result
        result = verified and response == 'restore'
        loop.quit()

    def verify():
        nonlocal verified, failure
        try:
            matches = [client for client in api.clients()
                       if client.get('class') == app_id and client.get('pid') == os.getpid()]
            if len(matches) == 1 and api.client_workspace(matches[0]) == workspace:
                verified = True
                dialog.set_response_enabled('restore', True)
                return False
            if len(matches) > 1 or matches or time.monotonic() >= deadline:
                raise RuntimeError('Browser recovery confirmation placement could not be verified')
        except (OSError, RuntimeError, ValueError) as error:
            failure = error
            loop.quit()
            return False
        return True

    dialog.connect('response', responded)
    timer = None
    try:
        with placement_rule(api.HYPRCTL, workspace, '^' + re.escape(app_id) + '$'):
            dialog.present()
            timer = GLib.timeout_add(50, verify)
            loop.run()
    finally:
        # A completed timeout removes itself; only remove a still-live source.
        if timer and GLib.MainContext.default().find_source_by_id(timer):
            GLib.source_remove(timer)
        dialog.destroy()
        application.remove_window(dialog)
    if failure:
        raise failure
    return result
