"""Disposable real GTK windows for the private compositor capability test."""
import argparse
from pathlib import Path
import json
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

parser = argparse.ArgumentParser()
parser.add_argument("--title", required=True)
parser.add_argument("--app-id", default="tablet-capability-fixture")
parser.add_argument("--confirm", action="store_true")
parser.add_argument("--click-file")
parser.add_argument("--second")
parser.add_argument("--churn-title", action="store_true")
parser.add_argument("--entry-file")
args = parser.parse_args()
GLib.set_prgname(args.app_id)

provider = Gtk.CssProvider()
provider.load_from_data(b"window { background-color: #15b94d; } button { padding: 24px; }")
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
windows = []


def create(title, confirm=False):
    window = Gtk.Window(title=title)
    window.set_default_size(480, 320)
    window.set_role("tablet-capability-fixture")
    button = Gtk.Button(label="Click-through fixture")
    count = [0]

    def clicked(_):
        count[0] += 1
        if args.click_file:
            Path(args.click_file).write_text(str(count[0]))

    button.connect("clicked", clicked)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.pack_start(Gtk.Label(label=title), True, True, 0)
    box.pack_start(button, False, False, 20)
    box.pack_start(Gtk.Label(label="Native fixture content"), True, True, 0)
    if args.entry_file:
        entry = Gtk.Entry()
        entry.set_placeholder_text("Private keyboard fixture")
        box.pack_start(entry, False, False, 24)
        def publish_entry(*_):
            coordinates = entry.translate_coordinates(window, 0, 0)
            if coordinates:
                allocation = entry.get_allocation()
                path = Path(args.entry_file)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(dict(x=coordinates[0], y=coordinates[1],
                    width=allocation.width, height=allocation.height, text=entry.get_text())))
                temporary.replace(path)
        entry.connect("changed", publish_entry)
        entry.connect("size-allocate", publish_entry)
    window.add(box)
    dialog = [None]

    def destroy(_):
        windows.remove(window)
        if not windows:
            Gtk.main_quit()

    def close(_window, _event):
        if not confirm:
            return False
        if dialog[0]:
            dialog[0].present()
            return True
        prompt = Gtk.MessageDialog(transient_for=window, modal=True,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text="Confirm close " + title)
        prompt.set_title("Confirm close " + title)
        prompt.set_default_response(Gtk.ResponseType.NO)
        dialog[0] = prompt

        def response(_prompt, result):
            dialog[0] = None
            prompt.destroy()
            if result == Gtk.ResponseType.YES:
                window.destroy()

        prompt.connect("response", response)
        prompt.show_all()
        return True

    window.connect("delete-event", close)
    window.connect("destroy", destroy)
    windows.append(window)
    window.show_all()
    if args.churn_title:
        revision = [0]

        def update_title():
            revision[0] += 1
            window.set_title(title + " " + str(revision[0]))
            return True

        GLib.timeout_add(5, update_title)


create(args.title, args.confirm)
if args.second:
    create(args.second)
Gtk.main()
