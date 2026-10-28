# Synthetic fixture lighting evidence

`create_scene.py` creates an anonymous ceiling fitting with a recessed diffuser, a non-light table and a separate locked manual light specification. It also exercises translated/rotated binding and deleted fixtures. No customer model is used. Generated BLEND, projections, native local views and Agent results belong in `artifacts/fixture-lighting/<run>/`, not this directory. They are reproducible and may be cleaned; this script is the persistent test input.

`check_inner_surface.py` builds a hollow shade with a top cap, an actual inner bulb and an obstructing pole. It verifies that component BVH anchors can reach the real bulb despite envelope occlusion, remain bounded, and retain outward normals after reflection. It writes its result only to the explicit artifact directory.
