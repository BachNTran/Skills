/**
 * Multiply two numbers.
 * @param a - first factor
 * @param b - second factor
 * @returns the product; see {@link add}
 */
export function mul(a: number, b: number): number {
  return a * b;
}

/** Add two numbers. */
export const add = (a: number, b: number): number => a + b;

/** A 2D vector. */
export interface Vec {
  x: number;
  y: number;
}

/** Either a number or a vector. */
export type Num = number | Vec;

/** Rounding modes. */
export enum Mode {
  Down,
  Nearest,
}

function internal(v: Vec): number {
  return mul(v.x, v.y);
}
