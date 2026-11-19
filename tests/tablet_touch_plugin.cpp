// Test-only input source. Never install or load into the desktop session.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/SeatManager.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <sstream>
#include <fstream>
#include <stdexcept>
#include <lua.hpp>

class TestTouch final : public ITouch {
  public:
    bool isVirtual() override { return true; }
    SP<Aquamarine::ITouch> aq() override { return {}; }
};
static SP<TestTouch> device;
static bool down = false;
static uint32_t now() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static SDispatchResult touch(std::string args) {
    std::istringstream input(args);
    std::string action, extra;
    double x = 0, y = 0;
    input >> action;
    if (action == "down" || action == "move") {
        if (!(input >> x >> y) || x < 0 || x > 1 || y < 0 || y > 1)
            return {.success = false, .error = "Expected normalized touch coordinates"};
    }
    if (input >> extra)
        return {.success = false, .error = "Unexpected touch arguments"};
    if (action == "down" && !down) {
        g_pInputManager->onTouchDown({.timeMs = now(), .touchID = 0, .pos = {x, y}, .device = device});
        down = true;
    } else if (action == "move" && down)
        g_pInputManager->onTouchMove({.timeMs = now(), .touchID = 0, .pos = {x, y}});
    else if (action == "up" && down) {
        g_pInputManager->onTouchUp({.timeMs = now(), .touchID = 0});
        down = false;
    } else
        return {.success = false, .error = "Invalid touch sequence"};
    g_pSeatManager->sendTouchFrame();
    std::ofstream trace(std::filesystem::path(std::getenv("TABLET_WINDOW_TEST_ROOT")) / "touch-routing.log", std::ios::app);
    const auto& data = g_pInputManager->m_touchData;
    trace << action << " " << x << " " << y << " global=" << data.lastTouchPos.x << "," << data.lastTouchPos.y
          << " layer=" << !data.touchFocusLS.expired() << " window=" << !data.touchFocusWindow.expired() << "\n";
    return {};
}
static int luaTouch(lua_State* L) {
    auto result = touch(luaL_checkstring(L, 1));
    if (!result.success) return luaL_error(L, "%s", result.error.c_str());
    lua_pushboolean(L, true);
    return 1;
}
static int luaSeatSnapshot(lua_State* L) {
    auto pid = [](const auto& weak) {
        pid_t value = 0;
        if (auto surface = weak.lock()) wl_client_get_credentials(surface->client(), &value, nullptr, nullptr);
        return value;
    };
    std::ofstream file(std::filesystem::path(std::getenv("TABLET_WINDOW_TEST_ROOT")) / "seat-focus.json");
    file << "{\"pointerPid\":" << pid(g_pSeatManager->m_state.pointerFocus)
         << ",\"keyboardPid\":" << pid(g_pSeatManager->m_state.keyboardFocus) << "}";
    lua_pushboolean(L, true);
    return 1;
}
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    const char* root = std::getenv("TABLET_WINDOW_TEST_ROOT");
    const char* runtime = std::getenv("XDG_RUNTIME_DIR");
    // Exact namespace/lifetime guards: production sessions must fail closed.
    if (!root || !runtime || !std::string(root).starts_with("/tmp/twa.proof.") ||
        std::filesystem::path(runtime) != std::filesystem::path(root) / "r" ||
        !std::filesystem::exists(std::filesystem::path(root) / "allow-test-touch"))
        throw std::runtime_error("Private tablet touch test only");
    device = makeShared<TestTouch>();
    device->m_self = device;
    device->m_hlName = device->m_deviceName = "tablet-private-touch";
    device->m_boundOutput = "eDP-1";
    g_pInputManager->m_touches.push_back(device);
    g_pInputManager->m_hids.push_back(device);
    g_pInputManager->updateCapabilities();
    if (!HyprlandAPI::addLuaFunction(handle, "tablet_test", "seat_snapshot", luaSeatSnapshot) ||
        !HyprlandAPI::addLuaFunction(handle, "tablet_test", "touch", luaTouch) ||
        !HyprlandAPI::addDispatcherV2(handle, "tablet-test-touch", touch))
        throw std::runtime_error("Touch test dispatcher registration failed");
    return {"tablet-test-touch", "Private compositor wl_touch injection", "Machine tests", "1"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    if (down) { g_pSeatManager->sendTouchCancel(); down = false; }
    if (device) { g_pInputManager->destroyTouchDevice(device); device.reset(); }
}
