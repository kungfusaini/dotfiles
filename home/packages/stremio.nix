{ stremio-linux-shell }:
# GApplication normally forwards activation to an existing singleton. Tablet
# launches must instead register atomically and refuse a remote owner, before
# starting even the streaming server. Ordinary desktop launches are unchanged.
stremio-linux-shell.overrideAttrs (old: {
  postPatch = (old.postPatch or "") + ''
    substituteInPlace src/main.rs \
      --replace-fail '    let mut server = Server::new();' '    let app = Application::new();
    let runtime = Runtime::new().expect("Failed to create Tokio runtime");
    let _guard = runtime.enter();
    if env::var_os("TABLET_STREMIO_TOKEN").is_some() {
        if gtk::prelude::ApplicationExt::register(&app, None::<&gtk::gio::Cancellable>).is_err()
            || gtk::prelude::ApplicationExt::is_remote(&app) {
            return ExitCode::FAILURE;
        }
    }
    let mut server = Server::new();' \
      --replace-fail $'    let app = Application::new();\n    app.set_property' '    app.set_property' \
      --replace-fail $'    let runtime = Runtime::new().expect("Failed to create Tokio runtime");\n    let _guard = runtime.enter();\n    app.run' '    app.run'
  '';
})
