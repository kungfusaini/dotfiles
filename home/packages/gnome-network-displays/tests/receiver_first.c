/* The selected production callbacks are injected below, not reimplemented. */
#include <gio/gio.h>

typedef GObject NdSink;
typedef GObject NdSinkRow;
typedef GObject GtkListBox;
typedef GObject XdpPortal;
typedef GObject XdpSession;
typedef GObject NdPulseaudio;
typedef void XdpParent;
G_DEFINE_AUTOPTR_CLEANUP_FUNC (NdSink, g_object_unref)

typedef struct {
  GObject parent;
  XdpPortal *portal;
  XdpSession *session;
  GCancellable *cancellable;
  NdPulseaudio *pulse;
  GObject *nm_device_registry;
  NdSink *pending_sink;
  NdSink *stream_sink;
  gboolean closing;
  GObject *find_sink_list;
  GObject *meta_provider;
  GObject *codec_install_video;
  GObject *codec_install_audio;
  GObject *error_firewall_zone;
  GListStore *connect_sink_list_model;
  GPtrArray *sink_property_bindings;
} NdWindow;
typedef GObjectClass NdWindowClass;
G_DEFINE_TYPE (NdWindow, test_window, G_TYPE_OBJECT)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (NdWindow, g_object_unref)

#define ND_WINDOW(p) ((NdWindow *)(p))
#define ND_PULSEAUDIO(p) ((GObject *)(p))
#define gnome_nd_window_parent_class test_window_parent_class
#define GTK_WIDGET(p) ((GObject *)(p))
#define GTK_WINDOW(p) ((GObject *)(p))
#define ND_IS_SINK_ROW(p) G_IS_OBJECT(p)
#define ND_PROVIDER(p) (p)
#define XDP_SESSION(p) (p)
#define XDP_PORTAL(p) (p)
#define XDP_OUTPUT_MONITOR 1
#define XDP_OUTPUT_WINDOW 2
#define XDP_OUTPUT_VIRTUAL 4
#define XDP_SCREENCAST_FLAG_NONE 0
#define XDP_CURSOR_MODE_EMBEDDED 1
#define XDP_PERSIST_MODE_NONE 0

static GPtrArray *creates, *starts;
static GList *available;
static guint portal_calls, create_calls, start_calls, stream_calls, close_calls, stop_calls, audio_unloads;
static gboolean portal_failure, stream_failure;
static NdSink *last_sink;

static void gnome_nd_window_finalize (GObject *object);
static void test_window_finalize (GObject *object) {
  NdWindow *w = ND_WINDOW(object);
  /* Only release fake template widgets here. All source-owned fields use the
   * actual production finalizer below, including a possibly absent pulse. */
  g_clear_object(&w->find_sink_list); g_clear_object(&w->codec_install_video);
  g_clear_object(&w->codec_install_audio); g_clear_object(&w->error_firewall_zone);
  g_clear_object(&w->connect_sink_list_model);
  gnome_nd_window_finalize(object);
}
static void test_window_class_init (NdWindowClass *class) {
  class->finalize = test_window_finalize;
}
static void test_window_init (NdWindow *w) {
  w->cancellable = g_cancellable_new();
  w->find_sink_list = g_object_new(G_TYPE_OBJECT, NULL);
  w->meta_provider = g_object_new(G_TYPE_OBJECT, NULL);
  w->connect_sink_list_model = g_list_store_new(G_TYPE_OBJECT);
  w->sink_property_bindings = g_ptr_array_new_with_free_func(g_object_unref);
  g_object_set_data(w->find_sink_list, "sensitive", GINT_TO_POINTER(TRUE));
}
static void gtk_widget_set_sensitive (GObject *widget, gboolean enabled) {
  g_object_set_data(widget, "sensitive", GINT_TO_POINTER(enabled));
}
static XdpPortal *xdp_portal_initable_new (GError **error) {
  portal_calls++;
  if (portal_failure) {
    g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "test portal unavailable");
    return NULL;
  }
  return g_object_new(G_TYPE_OBJECT, NULL);
}
static void xdp_portal_create_screencast_session (XdpPortal *portal, int outputs,
    int flags, int cursor, int persist, const char *token, GCancellable *cancel,
    GAsyncReadyCallback callback, gpointer data) {
  create_calls++;
  g_ptr_array_add(creates, g_task_new(portal, cancel, callback, data));
}
static XdpSession *xdp_portal_create_screencast_session_finish (XdpPortal *portal,
    GAsyncResult *result, GError **error) {
  return g_task_propagate_pointer(G_TASK(result), error);
}
static void xdp_session_start (XdpSession *session, XdpParent *parent,
    GCancellable *cancel, GAsyncReadyCallback callback, gpointer data) {
  start_calls++;
  g_ptr_array_add(starts, g_task_new(session, cancel, callback, data));
}
static gboolean xdp_session_start_finish (XdpSession *session,
    GAsyncResult *result, GError **error) {
  return g_task_propagate_boolean(G_TASK(result), error);
}
static XdpParent *xdp_parent_new_gtk (GObject *window) { return NULL; }
static void xdp_parent_free (XdpParent *parent) { }
static void xdp_session_close (XdpSession *session) {
  if (!g_object_get_data(session, "closed")) {
    g_object_set_data(session, "closed", GINT_TO_POINTER(TRUE));
    close_calls++;
    g_signal_emit_by_name(session, "closed");
  }
}
static NdSink *nd_sink_row_get_sink (NdSinkRow *row) { return g_object_get_data(row, "sink"); }
static GList *nd_provider_get_sinks (GObject *provider) { return g_list_copy(available); }
static NdSink *nd_sink_start_stream (NdSink *sink) {
  stream_calls++; last_sink = sink;
  return stream_failure ? NULL : g_object_ref(sink);
}
static void nd_sink_stop_stream (NdSink *sink) { stop_calls++; }
static void nd_pulseaudio_unload (NdPulseaudio *pulse) {
  g_assert_nonnull(pulse); audio_unloads++;
}
static gboolean audio_init_finish (GObject *source, GAsyncResult *result, GError **error) {
  return g_task_propagate_boolean(G_TASK(result), error);
}
#undef G_ASYNC_INITABLE
#define G_ASYNC_INITABLE(p) (p)
#define g_async_initable_init_finish audio_init_finish
static void sink_create_source_cb (void) { }
static void sink_create_audio_source_cb (void) { }
static void sink_notify_state_cb (NdWindow *self, GParamSpec *pspec, NdSink *sink) { }
/* Bindings are unchanged upstream UI plumbing, not the permission-flow subject. */
#undef g_object_bind_property
#undef g_object_bind_property_full
#define g_object_bind_property(...) g_object_new(G_TYPE_OBJECT, NULL)
#define g_object_bind_property_full(...) g_object_new(G_TYPE_OBJECT, NULL)
#define g_object_set(...) ((void)0)
static void nd_window_start_selected_sink (NdWindow *self);

/* PRODUCTION_CALLBACKS */

typedef struct { NdWindow *window; NdSink *a, *b; NdSinkRow *row_a, *row_b; } Fixture;
static void drain (void) { while (g_main_context_iteration(NULL, FALSE)); }
static GObject *object_with_signals (void) {
  /* One class for fake sessions/sinks; signals let real signal wiring execute. */
  static GType type;
  if (!type) {
    type = g_type_register_static_simple(G_TYPE_OBJECT, "TestReceiverObject",
                                         sizeof(GObjectClass), NULL, sizeof(GObject), NULL, 0);
    g_signal_new("closed", type, G_SIGNAL_RUN_LAST, 0, NULL, NULL, NULL, G_TYPE_NONE, 0);
    g_signal_new("create-source", type, G_SIGNAL_RUN_LAST, 0, NULL, NULL, NULL, G_TYPE_NONE, 0);
    g_signal_new("create-audio-source", type, G_SIGNAL_RUN_LAST, 0, NULL, NULL, NULL, G_TYPE_NONE, 0);
  }
  return g_object_new(type, NULL);
}
static void setup (Fixture *f, gconstpointer data) {
  creates = g_ptr_array_new(); starts = g_ptr_array_new();
  portal_calls = create_calls = start_calls = stream_calls = close_calls = stop_calls = audio_unloads = 0;
  portal_failure = stream_failure = FALSE; last_sink = NULL;
  f->window = g_object_new(test_window_get_type(), NULL);
  f->a = object_with_signals(); f->b = object_with_signals();
  f->row_a = g_object_new(G_TYPE_OBJECT, NULL); f->row_b = g_object_new(G_TYPE_OBJECT, NULL);
  g_object_set_data(f->row_a, "sink", f->a); g_object_set_data(f->row_b, "sink", f->b);
  available = g_list_append(g_list_append(NULL, f->a), f->b);
}
static void teardown (Fixture *f, gconstpointer data) {
  g_assert_cmpuint(creates->len, ==, 0); g_assert_cmpuint(starts->len, ==, 0);
  if (f->window) { nd_window_close_requested_cb(f->window); g_object_unref(f->window); }
  g_object_unref(f->a); g_object_unref(f->b); g_object_unref(f->row_a); g_object_unref(f->row_b);
  g_list_free(available); g_ptr_array_unref(creates); g_ptr_array_unref(starts);
}
static void select_a (Fixture *f) { find_sink_list_row_activated_cb(f->window, f->row_a, NULL); }
static void select_b (Fixture *f) { find_sink_list_row_activated_cb(f->window, f->row_b, NULL); }
static void finish_create (gboolean success) {
  GTask *task = g_ptr_array_steal_index(creates, 0);
  if (success) g_task_return_pointer(task, object_with_signals(), g_object_unref);
  else g_task_return_new_error(task, G_IO_ERROR, G_IO_ERROR_CANCELLED, "test cancelled");
  g_object_unref(task); drain();
}
static void finish_start (gboolean success) {
  GTask *task = g_ptr_array_steal_index(starts, 0);
  if (success) g_task_return_boolean(task, TRUE);
  else g_task_return_new_error(task, G_IO_ERROR, G_IO_ERROR_CANCELLED, "test cancelled");
  g_object_unref(task); drain();
}
static gboolean sensitive (Fixture *f) { return GPOINTER_TO_INT(g_object_get_data(f->window->find_sink_list, "sensitive")); }
static void assert_idle (Fixture *f) {
  g_assert_null(f->window->pending_sink); g_assert_null(f->window->session);
  g_assert_null(f->window->stream_sink); g_assert_true(sensitive(f));
}
static void selection (Fixture *f, gconstpointer data) {
  g_assert_cmpuint(create_calls, ==, 0);
  select_a(f); select_b(f);
  g_assert_true(f->window->pending_sink == f->a); g_assert_false(sensitive(f));
  g_assert_cmpuint(create_calls, ==, 1); g_assert_cmpuint(stream_calls, ==, 0);
  finish_create(TRUE);
  g_assert_cmpuint(start_calls, ==, 1); g_assert_cmpuint(stream_calls, ==, 0);
  finish_start(TRUE);
  g_assert_true(last_sink == f->a); g_assert_true(f->window->stream_sink == f->a);
  g_assert_cmpuint(stream_calls, ==, 1); g_assert_null(f->window->pending_sink);
}
static void create_cancel (Fixture *f, gconstpointer data) {
  select_a(f); finish_create(FALSE); assert_idle(f);
  g_assert_cmpuint(stream_calls, ==, 0); g_assert_cmpuint(start_calls, ==, 0);
}
static void start_cancel_retry (Fixture *f, gconstpointer data) {
  select_a(f); finish_create(TRUE); finish_start(FALSE); assert_idle(f);
  g_assert_cmpuint(stream_calls, ==, 0); g_assert_cmpuint(close_calls, ==, 1);
  select_b(f); finish_create(TRUE); finish_start(TRUE);
  g_assert_true(last_sink == f->b); g_assert_cmpuint(stream_calls, ==, 1);
}
static void receiver_removed (Fixture *f, gconstpointer data) {
  select_a(f); finish_create(TRUE); available = g_list_remove(available, f->a);
  finish_start(TRUE); assert_idle(f); g_assert_cmpuint(stream_calls, ==, 0);
}
static void close_during_create (Fixture *f, gconstpointer data) {
  select_a(f); nd_window_close_requested_cb(f->window);
  GWeakRef weak; g_weak_ref_init(&weak, f->window);
  g_clear_object(&f->window); finish_create(TRUE);
  GObject *remaining = g_weak_ref_get(&weak); g_assert_null(remaining); g_weak_ref_clear(&weak);
  g_assert_cmpuint(stream_calls, ==, 0);
}
static void close_during_start (Fixture *f, gconstpointer data) {
  select_a(f); finish_create(TRUE); nd_window_close_requested_cb(f->window);
  GWeakRef weak; g_weak_ref_init(&weak, f->window);
  g_clear_object(&f->window); finish_start(TRUE);
  GObject *remaining = g_weak_ref_get(&weak); g_assert_null(remaining); g_weak_ref_clear(&weak);
  g_assert_cmpuint(stream_calls, ==, 0);
}
static void stale_start (Fixture *f, gconstpointer data) {
  select_a(f); finish_create(TRUE);
  g_autoptr(GObject) old = g_object_ref(f->window->session);
  xdp_session_close(old); assert_idle(f);
  select_b(f); finish_create(TRUE);
  XdpSession *current = f->window->session;
  finish_start(TRUE); /* Old request completes after the new selection. */
  g_assert_true(f->window->pending_sink == f->b); g_assert_true(f->window->session == current);
  session_closed_cb(f->window, old);
  g_assert_true(f->window->session == current);
  finish_start(TRUE); g_assert_true(last_sink == f->b); g_assert_cmpuint(stream_calls, ==, 1);
}
static void portal_error (Fixture *f, gconstpointer data) {
  portal_failure = TRUE; select_a(f); assert_idle(f);
  g_assert_cmpuint(create_calls, ==, 0); g_assert_cmpuint(stream_calls, ==, 0);
  portal_failure = FALSE; select_b(f); finish_create(TRUE); finish_start(TRUE);
  g_assert_true(last_sink == f->b);
}
static void stream_error (Fixture *f, gconstpointer data) {
  stream_failure = TRUE; select_a(f); finish_create(TRUE); finish_start(TRUE);
  assert_idle(f); g_assert_cmpuint(close_calls, ==, 1);
}
static void audio_close (Fixture *f, gconstpointer race) {
  GObject *pulse = g_object_new(G_TYPE_OBJECT, NULL);
  GWeakRef window_weak, pulse_weak;
  g_weak_ref_init(&window_weak, f->window); g_weak_ref_init(&pulse_weak, pulse);
  /* NULL cancellable models completion racing with close, returning success. */
  GTask *task = g_task_new(pulse, race ? NULL : f->window->cancellable,
                           nd_pulseaudio_init_async_cb, g_object_ref(f->window));
  nd_window_close_requested_cb(f->window); g_clear_object(&f->window);
  g_task_return_boolean(task, TRUE); g_object_unref(task); drain();
  g_assert_null(g_weak_ref_get(&window_weak)); g_assert_null(g_weak_ref_get(&pulse_weak));
  g_weak_ref_clear(&window_weak); g_weak_ref_clear(&pulse_weak);
  g_assert_cmpuint(audio_unloads, ==, 1);
}
static void audio_success (Fixture *f, gconstpointer data) {
  GObject *pulse = g_object_new(G_TYPE_OBJECT, NULL);
  GTask *task = g_task_new(pulse, f->window->cancellable,
                           nd_pulseaudio_init_async_cb, g_object_ref(f->window));
  g_task_return_boolean(task, TRUE); g_object_unref(task); drain();
  g_assert_true(f->window->pulse == pulse); g_assert_cmpuint(audio_unloads, ==, 0);
  nd_window_close_requested_cb(f->window); g_clear_object(&f->window);
  g_assert_cmpuint(audio_unloads, ==, 1);
}
int main (int argc, char **argv) {
  g_test_init(&argc, &argv, NULL);
  g_log_set_always_fatal(G_LOG_LEVEL_ERROR | G_LOG_LEVEL_CRITICAL);
#define TEST(name, fn) g_test_add(name, Fixture, NULL, setup, fn, teardown)
  TEST("/receiver/selection-before-permission", selection);
  TEST("/receiver/create-cancel", create_cancel);
  TEST("/receiver/start-cancel-and-retry", start_cancel_retry);
  TEST("/receiver/disappears", receiver_removed);
  TEST("/receiver/close-during-create", close_during_create);
  TEST("/receiver/close-during-start", close_during_start);
  TEST("/receiver/stale-callback-after-retry", stale_start);
  TEST("/receiver/portal-error-no-fallback", portal_error);
  TEST("/receiver/stream-error", stream_error);
  TEST("/receiver/close-during-audio-init", audio_close);
  g_test_add("/receiver/audio-success-racing-close", Fixture, GINT_TO_POINTER(1), setup, audio_close, teardown);
  TEST("/receiver/audio-success-finalizes-once", audio_success);
  return g_test_run();
}
