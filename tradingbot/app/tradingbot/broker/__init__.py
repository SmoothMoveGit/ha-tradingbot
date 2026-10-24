from .base import Account, Bar, Broker, Position

__all__ = ["Account", "Bar", "Broker", "Position", "make_broker"]


def make_broker(cfg):
    if cfg.mode == "sim":
        from .sim import SimBroker
        return SimBroker(cash=cfg.risk.start_budget, symbols=cfg.watchlist)
    from .alpaca import AlpacaBroker
    return AlpacaBroker(cfg.alpaca_key, cfg.alpaca_secret, paper=cfg.mode != "live")
