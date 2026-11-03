(() => {
  const homeAdVideoSelector = [
    '[data-testid="home-ad-video-asset"] video',
    '[data-testid="home-ads-container"] video',
  ].join(", ");

  const installFocusAwareMotion = () => {
    const paused = new Set();

    const sync = () => {
      if (document.hasFocus()) {
        for (const animation of paused) {
          if (animation.playState === "paused" && animation.effect?.target?.isConnected) {
            animation.play();
          }
        }
        paused.clear();
        return;
      }

      for (const animation of paused) {
        if (animation.playState !== "paused" || !animation.effect?.target?.isConnected) {
          paused.delete(animation);
        }
      }

      // Only infinite CSS loops are decorative. Finite animations, transitions,
      // and script/scroll-driven animations may be required for UI completion.
      for (const animation of document.getAnimations()) {
        if (
          animation instanceof CSSAnimation &&
          animation.timeline instanceof DocumentTimeline &&
          animation.effect?.getTiming().iterations === Infinity &&
          animation.playState === "running"
        ) {
          animation.pause();
          paused.add(animation);
        }
      }
    };

    window.addEventListener("focus", sync);
    window.addEventListener("blur", sync);
    document.addEventListener("animationstart", sync, true);
    sync();
  };

  const stopAutoplay = (video) => {
    if (!(video instanceof HTMLVideoElement)) return;
    if (!video.muted || !(video.autoplay || video.hasAttribute("autoplay"))) return;
    video.autoplay = false;
    video.removeAttribute("autoplay");
    if (!video.paused) video.pause();
  };

  const scan = (root) => {
    if (!(root instanceof Element || root instanceof Document)) return;
    if (root instanceof Element && root.matches(homeAdVideoSelector)) stopAutoplay(root);
    root.querySelectorAll(homeAdVideoSelector).forEach(stopAutoplay);
  };

  const start = () => {
    installFocusAwareMotion();
    scan(document);

    document.addEventListener(
      "play",
      (event) => {
        const video = event.target;
        if (video instanceof HTMLVideoElement && video.matches(homeAdVideoSelector)) stopAutoplay(video);
      },
      true,
    );

    new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) scan(node);
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
