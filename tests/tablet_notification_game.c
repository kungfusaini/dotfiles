/* Private SDL input witness: never opens a host display or account/profile. */
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned keys, clicks, motions;
static const char *state;
static SDL_Window *window;
static void report(void) {
    char temporary[4096];
    if (snprintf(temporary, sizeof temporary, "%s.tmp", state) >= (int)sizeof temporary) exit(2);
    FILE *f = fopen(temporary, "w");
    if (!f) exit(2);
    fprintf(f, "{\"keys\":%u,\"clicks\":%u,\"motions\":%u,\"focused\":%s,\"relative\":%s,\"driver\":\"%s\"}\n",
            keys, clicks, motions, (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) ? "true" : "false",
            SDL_GetRelativeMouseMode() ? "true" : "false", SDL_GetCurrentVideoDriver());
    fclose(f);
    if (rename(temporary, state)) exit(2);
}
int main(void) {
    state = getenv("TABLET_NOTIFICATION_GAME_STATE");
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    const char *control = getenv("TABLET_NOTIFICATION_GAME_CONTROL");
    if (!state || !runtime || !control || strncmp(runtime, "/tmp/twa.proof.", 15) ||
        strncmp(state, runtime, strlen(runtime)) || strncmp(control, runtime, strlen(runtime))) return 2;
    SDL_SetHint("SDL_VIDEO_WAYLAND_WMCLASS", "tablet-notification-game");
    SDL_SetHint("SDL_VIDEO_X11_WMCLASS", "tablet-notification-game");
    SDL_SetHint(SDL_HINT_MOUSE_FOCUS_CLICKTHROUGH, "1");
    if (SDL_Init(SDL_INIT_VIDEO)) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
    window = SDL_CreateWindow("Tablet fixture game", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
                              480, 320, SDL_WINDOW_RESIZABLE);
    if (!window) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
    /* SDL2 starts text input by default; this game witness has no text field. */
    SDL_StopTextInput();
    SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
    int running = 1, requested_relative = 0;
    while (running) {
        FILE *input = fopen(control, "r");
        int requested = input ? fgetc(input) == '1' : 0;
        if (input) fclose(input);
        if (requested != requested_relative) {
            if (SDL_SetRelativeMouseMode(requested ? SDL_TRUE : SDL_FALSE)) {
                fprintf(stderr, "Relative mode: %s\n", SDL_GetError()); return 1;
            }
            requested_relative = requested;
        }
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            switch (e.type) {
            case SDL_QUIT: running = 0; break;
            case SDL_KEYDOWN:
                ++keys;
                break;
            case SDL_MOUSEBUTTONDOWN: ++clicks; break;
            case SDL_MOUSEMOTION: ++motions; break;
            }
        }
        SDL_SetRenderDrawColor(renderer, 21, 185, 77, 255);
        SDL_RenderClear(renderer);
        /* Recorded input acknowledgements, not just a focused-window flag:
         * blue grows on keys, orange on buttons; white marks relative mode. */
        SDL_Rect key_bar = {24, 80, 16 + (int)(keys % 20) * 18, 24};
        SDL_Rect click_bar = {24, 120, 16 + (int)(clicks % 20) * 18, 24};
        SDL_SetRenderDrawColor(renderer, 25, 70, 220, 255); SDL_RenderFillRect(renderer, &key_bar);
        SDL_SetRenderDrawColor(renderer, 245, 135, 25, 255); SDL_RenderFillRect(renderer, &click_bar);
        if (SDL_GetRelativeMouseMode()) {
            SDL_Rect lock = {24, 160, 24, 24};
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255); SDL_RenderFillRect(renderer, &lock);
        }
        SDL_RenderPresent(renderer);
        report(); SDL_Delay(10);
    }
    SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit();
    return 0;
}
