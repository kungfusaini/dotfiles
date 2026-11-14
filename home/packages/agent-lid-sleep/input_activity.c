/* Report idle/activity only, never keys or pointer coordinates. */
#include <stdio.h>
#include <string.h>
#include <wayland-client.h>
#include "ext-idle-notify-v1-client-protocol.h"

static struct ext_idle_notifier_v1 *notifier;
static struct wl_seat *seat;
static uint32_t notifier_name, seat_name;
static int removed;

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data;
    if (!strcmp(interface, ext_idle_notifier_v1_interface.name) && version >= 2) {
        notifier = wl_registry_bind(registry, name, &ext_idle_notifier_v1_interface, 2);
        notifier_name = name;
    } else if (!seat && !strcmp(interface, wl_seat_interface.name)) {
        seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
        seat_name = name;
    }
}

static void global_remove(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data;
    (void)registry;
    if (name == notifier_name || name == seat_name)
        removed = 1;
}

static void idled(void *data, struct ext_idle_notification_v1 *notification) {
    (void)data;
    (void)notification;
    puts("idle");
    fflush(stdout);
}

static void resumed(void *data, struct ext_idle_notification_v1 *notification) {
    (void)data;
    (void)notification;
    puts("active");
    fflush(stdout);
}

int main(void) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display)
        return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    const struct wl_registry_listener registry_listener = {global, global_remove};
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !notifier || !seat) {
        fputs("Input idle notification v2 and a seat are required\n", stderr);
        wl_display_disconnect(display);
        return 1;
    }
    /* Positive timeout is important: Hyprland does not resume a zero-ms timer.
     * Ignore media idle inhibitors for this explicitly requested action.
     * Initial idle allows the invoking shortcut's releases to settle. */
    struct ext_idle_notification_v1 *notification =
        ext_idle_notifier_v1_get_input_idle_notification(notifier, 250, seat);
    const struct ext_idle_notification_v1_listener listener = {idled, resumed};
    ext_idle_notification_v1_add_listener(notification, &listener, NULL);
    while (!removed && wl_display_dispatch(display) >= 0) {}
    wl_display_disconnect(display);
    return 1; /* Lost activity observation must never authorize sleep. */
}
