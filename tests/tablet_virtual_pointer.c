// Persistent private-test pointer. Unlike one-shot clients, the seat/device
// remains alive between motion and button events on the nested compositor.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
    (void)data;
    if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
        manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, version > 2 ? 2 : version);
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {(void)data;(void)registry;(void)name;}
int main(void) {
    if (!getenv("TABLET_WINDOW_TEST_ROOT")) return 4;
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    const struct wl_registry_listener listener = {.global=global,.global_remove=removed};
    wl_registry_add_listener(registry,&listener,NULL);
    wl_display_roundtrip(display);
    if (!manager) return 2;
    struct zwlr_virtual_pointer_v1 *pointer=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager,NULL);
    wl_display_roundtrip(display);
    char line[128];
    puts("READY");fflush(stdout);
    while (fgets(line,sizeof(line),stdin)) {
        struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
        uint32_t ms=(uint32_t)(now.tv_sec*1000+now.tv_nsec/1000000);
        unsigned x,y,w,h;
        if (sscanf(line,"move %u %u %u %u",&x,&y,&w,&h)==4)
            zwlr_virtual_pointer_v1_motion_absolute(pointer,ms,x,y,w,h);
        else if (!strncmp(line,"down",4)) zwlr_virtual_pointer_v1_button(pointer,ms,0x110,WL_POINTER_BUTTON_STATE_PRESSED);
        else if (!strncmp(line,"up",2)) zwlr_virtual_pointer_v1_button(pointer,ms,0x110,WL_POINTER_BUTTON_STATE_RELEASED);
        else return 3;
        zwlr_virtual_pointer_v1_frame(pointer);
        wl_display_roundtrip(display);
        puts("OK");fflush(stdout);
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    wl_display_disconnect(display);
    return 0;
}
