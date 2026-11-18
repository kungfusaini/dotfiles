#include <gst/gst.h>

/* Use linked GStreamer, not gst-launch's own wrapper/plugin defaults. */
int main(int argc, char **argv) {
    gst_init(&argc, &argv);
    GError *error = NULL;
    GstElement *pipeline = gst_parse_launch(
        "videotestsrc num-buffers=5 ! queue ! videoconvert ! "
        "x264enc tune=zerolatency ! h264parse ! fakesink", &error);
    if (error || !pipeline) {
        g_printerr("linked pipeline parse failed: %s\n",
                   error ? error->message : "no pipeline");
        g_clear_error(&error);
        if (pipeline) gst_object_unref(pipeline);
        return 1;
    }
    GstStateChangeReturn state = gst_element_set_state(pipeline, GST_STATE_PLAYING);
    GstBus *bus = gst_element_get_bus(pipeline);
    GstMessage *message = state == GST_STATE_CHANGE_FAILURE ? NULL :
        gst_bus_timed_pop_filtered(bus, 10 * GST_SECOND,
                                  GST_MESSAGE_EOS | GST_MESSAGE_ERROR);
    int failed = !message || GST_MESSAGE_TYPE(message) != GST_MESSAGE_EOS;
    if (message && GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
        gst_message_parse_error(message, &error, NULL);
        g_printerr("linked pipeline failed: %s\n", error->message);
        g_clear_error(&error);
    } else if (!message) {
        g_printerr("linked pipeline failed to reach EOS\n");
    }
    if (message) gst_message_unref(message);
    gst_element_set_state(pipeline, GST_STATE_NULL);
    gst_object_unref(bus);
    gst_object_unref(pipeline);
    return failed;
}
