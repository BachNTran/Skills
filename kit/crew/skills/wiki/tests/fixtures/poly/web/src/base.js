/** Base class for widgets. */
export class Base {
  constructor(el) {
    this.el = el;
  }

  /** Draw nothing; subclasses override. */
  render() {
    return "";
  }
}
