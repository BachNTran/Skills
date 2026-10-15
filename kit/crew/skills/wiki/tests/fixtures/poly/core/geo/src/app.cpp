#include <cstdio>
#include "geo/circle.hpp"

namespace ui {
struct Point;  // forward declaration, not geo::Point
}

#if 0
void dead_code() {
#endif

namespace geo {

Shape* make(Kind k, double size) {
  if (k == Kind::circle) return new Circle(size);
  return nullptr;
}

/// Sum of two points.
Point operator+(const Point& a, const Point& b) {
  return Point{a.x + b.x, a.y + b.y};
}

}  // namespace geo

/// Print the area of every shape.
int run_app() {
  geo::Shape* s = geo::make(geo::Kind::circle, 2.0);
  auto report = [&](double v) { std::printf("%f\n", v); };
  report(s->area());
  geo::Point p = geo::Point{1, 2} + geo::Point{3, 4};
  delete s;
  return p.norm() > 0 ? 0 : 1;
}
