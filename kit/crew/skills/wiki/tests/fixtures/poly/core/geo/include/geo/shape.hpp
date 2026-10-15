#pragma once
#include <string>

namespace geo {
namespace detail {
inline double square(double v) { return v * v; }
}  // namespace detail

/// A point on the plane, in metres.
struct Point {
  double x = 0;  ///< east offset
  double y = 0;  ///< north offset
  double norm() const { return detail::square(x) + detail::square(y); }
};

/** Shape kinds the factory can build. */
enum class Kind : unsigned char { circle, square };

/**
 * @brief Abstract planar shape.
 */
class Shape {
 public:
  virtual ~Shape() = default;
  /**
   * @brief Area of the shape.
   * @return area in square metres
   */
  virtual double area() const = 0;
  /// Human-readable name.
  virtual std::string name() const { return "shape"; }

 protected:
  Point origin_;
};

/// Largest of two values.
template <typename T>
T largest(T a, T b) {
  return a < b ? b : a;
}

Shape* make(Kind k, double size);

}  // namespace geo
