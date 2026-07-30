from vision_agents.core.events.manager import EventManager

def patch_event_manager():
    """
    Monkey-patch EventManager to resolve NoneType startswith AttributeError on Render.
    """
    def safe_register_events_from_module(self, module, prefix="", ignore_not_compatible=True):
        for name, class_ in module.__dict__.items():
            if name.endswith("Event"):
                evt_type = getattr(class_, "type", "")
                if evt_type is None:
                    evt_type = ""
                if not prefix or evt_type.startswith(prefix):
                    self.register(class_, ignore_not_compatible=ignore_not_compatible)
                    self._modules.setdefault(module.__name__, []).append(class_)

    EventManager.register_events_from_module = safe_register_events_from_module
