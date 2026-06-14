__all__ = ["display_nearby_aircraft", "build_route_info_text"]


def __getattr__(name: str):
	if name in __all__:
		module = __import__(f"{__name__}.near_sky", fromlist=[name])
		return getattr(module, name)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
	return __all__[:]  # keep exports minimal and explicit
