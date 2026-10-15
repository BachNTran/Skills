import { Base } from "./base.js";

const SPLIT = /}/g;

/**
 * A widget that renders text.
 */
export default class Widget extends Base {
  static count = 0;
  #secret = 1;

  /**
   * @param {string} el - mount point
   */
  constructor(el) {
    super(el);
    this.parts = [];
    Widget.count += 1;
  }

  /** Render the widget. */
  render() {
    const ratio = this.parts.length / 2;
    return this.#format(ratio) + SPLIT.source;
  }

  /** Render again. */
  refresh() {
    return this.render();
  }

  #format(v) {
    return `${v}`;
  }

  /** Make a widget. */
  static create(el) {
    const w = new Widget(el);
    w.render();
    return w;
  }
}
