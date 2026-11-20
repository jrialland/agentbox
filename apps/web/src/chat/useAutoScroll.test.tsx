import { act, fireEvent, renderHook } from "@testing-library/react";
import { useRef } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { useAutoScroll } from "./useAutoScroll";

function makeScroller() {
  const el = document.createElement("div");
  let top = 1000;
  Object.defineProperty(el, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: 100, configurable: true });
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => top,
    set: (value: number) => {
      top = value;
    },
  });
  el.scrollTo = ((options: ScrollToOptions | number) => {
    top = typeof options === "number" ? options : (options.top ?? top);
  }) as typeof el.scrollTo;
  document.body.append(el);
  return {
    el,
    get top() {
      return top;
    },
    set top(value: number) {
      top = value;
    },
  };
}

describe("useAutoScroll", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("follows new content while at the bottom", () => {
    const scroller = makeScroller();
    const { rerender } = renderHook(
      ({ n }: { n: number }) => {
        const ref = useRef<HTMLDivElement>(scroller.el);
        return useAutoScroll(ref, [n]);
      },
      { initialProps: { n: 0 } },
    );

    expect(scroller.top).toBe(1000);
    act(() => {
      scroller.el.scrollTop = 900;
    });
    rerender({ n: 1 });
    expect(scroller.top).toBe(1000);
  });

  it("stays put when scrolled up, then jumps to latest", () => {
    const scroller = makeScroller();
    const { result, rerender } = renderHook(
      ({ n }: { n: number }) => {
        const ref = useRef<HTMLDivElement>(scroller.el);
        return useAutoScroll(ref, [n]);
      },
      { initialProps: { n: 0 } },
    );

    act(() => {
      scroller.el.scrollTop = 0;
      fireEvent.scroll(scroller.el);
    });
    expect(result.current.atBottom).toBe(false);

    scroller.top = 0;
    rerender({ n: 1 });
    expect(scroller.top).toBe(0);

    act(() => result.current.scrollToBottom());
    expect(scroller.top).toBe(1000);
    expect(result.current.atBottom).toBe(true);
  });
});
