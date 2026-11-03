import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../hosts/kirax1/modules/desktop/spotify-power-saver.js", import.meta.url), "utf8");

function harness(focused = false) {
  const listeners = new Map();
  const animations = [];
  class DocumentTimeline {}
  class CSSAnimation {
    constructor({ iterations = Infinity, state = "running", timeline = new DocumentTimeline() } = {}) {
      this.playState = state;
      this.timeline = timeline;
      this.effect = { target: { isConnected: true }, getTiming: () => ({ iterations }) };
    }
    pause() { this.playState = "paused"; }
    play() { this.playState = "running"; }
  }
  const listen = (name, fn) => listeners.set(name, fn);
  const document = {
    readyState: "complete",
    documentElement: {},
    hasFocus: () => focused,
    getAnimations: () => animations,
    querySelectorAll: () => [],
    addEventListener: listen,
  };
  vm.runInNewContext(source, {
    document,
    window: { addEventListener: listen },
    Document: class { static [Symbol.hasInstance](value) { return value === document; } },
    Element: class {},
    HTMLVideoElement: class {},
    CSSAnimation,
    DocumentTimeline,
    MutationObserver: class { observe() {} },
  });
  return {
    animations, CSSAnimation,
    emit(name) { listeners.get(name)?.(); },
    focus(value) { focused = value; listeners.get(value ? "focus" : "blur")(); },
  };
}

test("pauses newly started infinite CSS loops while unfocused and resumes on focus", () => {
  const h = harness();
  const loop = new h.CSSAnimation();
  h.animations.push(loop);
  h.emit("animationstart");
  assert.equal(loop.playState, "paused");
  h.focus(true);
  assert.equal(loop.playState, "running");
  h.focus(false);
  assert.equal(loop.playState, "paused");
});

test("leaves finite, script-driven, scroll-driven, and already paused animations alone", () => {
  const h = harness();
  const finite = new h.CSSAnimation({ iterations: 1 });
  const scroll = new h.CSSAnimation({ timeline: {} });
  const paused = new h.CSSAnimation({ state: "paused" });
  const script = { playState: "running", pause() { assert.fail("script animation paused"); } };
  h.animations.push(finite, scroll, paused, script);
  h.emit("animationstart");
  assert.equal(finite.playState, "running");
  assert.equal(scroll.playState, "running");
  h.focus(true);
  assert.equal(paused.playState, "paused");
});

test("does not restart canceled or detached loops on focus", () => {
  const h = harness();
  const canceled = new h.CSSAnimation(), detached = new h.CSSAnimation();
  h.animations.push(canceled, detached);
  h.emit("animationstart");
  canceled.playState = "idle";
  detached.effect.target.isConnected = false;
  h.focus(true);
  assert.equal(canceled.playState, "idle");
  assert.equal(detached.playState, "paused");
});

test("does not suppress loops started while focused", () => {
  const h = harness(true), loop = new h.CSSAnimation();
  h.animations.push(loop);
  h.emit("animationstart");
  assert.equal(loop.playState, "running");
});
