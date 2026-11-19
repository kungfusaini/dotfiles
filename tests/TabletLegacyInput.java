/* Private input witness using the installed game's libGDX/LWJGL classes,
 * not its main class, saves, preferences, Steam API or gameplay code. */
import com.badlogic.gdx.ApplicationAdapter;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.InputAdapter;
import com.badlogic.gdx.backends.lwjgl.LwjglApplication;
import com.badlogic.gdx.backends.lwjgl.LwjglApplicationConfiguration;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public final class TabletLegacyInput extends ApplicationAdapter {
    private int keys, clicks, releases, motions;
    private Path state, control;
    private boolean relative;

    @Override public void create() {
        String runtime = System.getenv("XDG_RUNTIME_DIR");
        state = Paths.get(System.getenv("TABLET_NOTIFICATION_GAME_STATE"));
        control = Paths.get(System.getenv("TABLET_NOTIFICATION_GAME_CONTROL"));
        if (runtime == null || !runtime.startsWith("/tmp/twa.proof.")
                || !state.startsWith(runtime) || !control.startsWith(runtime))
            throw new IllegalStateException("Private compositor only");
        Gdx.input.setInputProcessor(new InputAdapter() {
            @Override public boolean keyDown(int key) { keys++; return true; }
            @Override public boolean touchDown(int x, int y, int pointer, int button) { clicks++; return true; }
            @Override public boolean touchUp(int x, int y, int pointer, int button) { releases++; return true; }
            @Override public boolean mouseMoved(int x, int y) { motions++; return true; }
            @Override public boolean touchDragged(int x, int y, int pointer) { motions++; return true; }
        });
    }

    @Override public void render() {
        try {
            boolean requested = new String(Files.readAllBytes(control), StandardCharsets.UTF_8).startsWith("1");
            if (requested != relative) {
                Gdx.input.setCursorCatched(requested);
                relative = requested;
            }
            Gdx.gl.glClearColor(21f/255, 185f/255, 77f/255, 1);
            Gdx.gl.glClear(0x4000);
            String json = String.format(java.util.Locale.ROOT,
                "{\"keys\":%d,\"clicks\":%d,\"releases\":%d,\"motions\":%d,\"touches\":0,\"pressed\":%s,\"focused\":%s,\"relative\":%s,\"driver\":\"lwjgl2-x11\"}\n",
                keys, clicks, releases, motions, Gdx.input.isTouched(), org.lwjgl.opengl.Display.isActive(), relative);
            Path tmp = Paths.get(state.toString()+".tmp");
            Files.write(tmp, json.getBytes(StandardCharsets.UTF_8));
            Files.move(tmp, state, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception error) {
            throw new RuntimeException(error);
        }
    }

    public static void main(String[] args) {
        LwjglApplicationConfiguration.disableAudio = true;
        LwjglApplicationConfiguration config = new LwjglApplicationConfiguration();
        config.title = "Tablet fixture game";
        config.width = 480;
        config.height = 320;
        config.allowSoftwareMode = true;
        config.foregroundFPS = config.backgroundFPS = 60;
        new LwjglApplication(new TabletLegacyInput(), config);
    }
}
