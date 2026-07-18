"""Hot convex-polygon kernels shared by geometry feasibility checks."""

from __future__ import annotations

import math

from dot.acceleration import compiled

_EPSILON = 1e-9


@compiled
def convex_polygons_overlap(left: tuple, right: tuple) -> bool:
    """Return whether convex polygons overlap with positive area (SAT)."""

    for side in range(2):
        polygon = left if side == 0 else right
        for index in range(len(polygon)):
            next_index = 0 if index + 1 == len(polygon) else index + 1
            normal_x = -(polygon[next_index][1] - polygon[index][1])
            normal_y = polygon[next_index][0] - polygon[index][0]
            length = math.sqrt(normal_x * normal_x + normal_y * normal_y)
            if length <= _EPSILON:
                continue
            normal_x /= length
            normal_y /= length

            left_min = left_max = left[0][0] * normal_x + left[0][1] * normal_y
            for point_index in range(1, len(left)):
                projection = (
                    left[point_index][0] * normal_x
                    + left[point_index][1] * normal_y
                )
                if projection < left_min:
                    left_min = projection
                if projection > left_max:
                    left_max = projection

            right_min = right_max = (
                right[0][0] * normal_x + right[0][1] * normal_y
            )
            for point_index in range(1, len(right)):
                projection = (
                    right[point_index][0] * normal_x
                    + right[point_index][1] * normal_y
                )
                if projection < right_min:
                    right_min = projection
                if projection > right_max:
                    right_max = projection

            overlap = min(left_max, right_max) - max(left_min, right_min)
            if overlap <= _EPSILON:
                return False
    return True


@compiled
def convex_polygon_overlap_depth(left: tuple, right: tuple) -> float:
    """Return the minimum SAT penetration depth of two convex polygons."""

    minimum_depth = math.inf
    found_axis = False
    for side in range(2):
        polygon = left if side == 0 else right
        for index in range(len(polygon)):
            next_index = 0 if index + 1 == len(polygon) else index + 1
            normal_x = -(polygon[next_index][1] - polygon[index][1])
            normal_y = polygon[next_index][0] - polygon[index][0]
            length = math.sqrt(normal_x * normal_x + normal_y * normal_y)
            if length <= _EPSILON:
                continue
            normal_x /= length
            normal_y /= length
            found_axis = True

            left_min = left_max = left[0][0] * normal_x + left[0][1] * normal_y
            for point_index in range(1, len(left)):
                projection = (
                    left[point_index][0] * normal_x
                    + left[point_index][1] * normal_y
                )
                if projection < left_min:
                    left_min = projection
                if projection > left_max:
                    left_max = projection

            right_min = right_max = (
                right[0][0] * normal_x + right[0][1] * normal_y
            )
            for point_index in range(1, len(right)):
                projection = (
                    right[point_index][0] * normal_x
                    + right[point_index][1] * normal_y
                )
                if projection < right_min:
                    right_min = projection
                if projection > right_max:
                    right_max = projection

            depth = min(left_max, right_max) - max(left_min, right_min)
            if depth < minimum_depth:
                minimum_depth = depth

    if not found_axis or minimum_depth <= 0.0:
        return 0.0
    return minimum_depth


@compiled
def convex_polygon_distance(left: tuple, right: tuple) -> float:
    """Return the exact closest-point distance of two disjoint polygons."""

    minimum_squared = math.inf
    for direction in range(2):
        vertices = left if direction == 0 else right
        edges = right if direction == 0 else left
        for vertex in vertices:
            for edge_index in range(len(edges)):
                next_index = 0 if edge_index + 1 == len(edges) else edge_index + 1
                start = edges[edge_index]
                end = edges[next_index]
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length_squared = dx * dx + dy * dy
                if length_squared <= _EPSILON:
                    closest_x = start[0]
                    closest_y = start[1]
                else:
                    parameter = (
                        (vertex[0] - start[0]) * dx
                        + (vertex[1] - start[1]) * dy
                    ) / length_squared
                    parameter = min(1.0, max(0.0, parameter))
                    closest_x = start[0] + parameter * dx
                    closest_y = start[1] + parameter * dy
                distance_x = vertex[0] - closest_x
                distance_y = vertex[1] - closest_y
                distance_squared = (
                    distance_x * distance_x + distance_y * distance_y
                )
                if distance_squared < minimum_squared:
                    minimum_squared = distance_squared

    return math.sqrt(minimum_squared)
