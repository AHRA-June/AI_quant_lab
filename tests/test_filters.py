"""DQ.3 security-type filters."""

from quantlab.data.filters import is_common_stock, is_preferred, is_reit, is_spac

ETF = frozenset({"069500"})


def test_preferred_detected_by_suffix_and_name():
    assert is_preferred("005935", "삼성전자우")  # both signals
    assert is_preferred("005935", "삼성전자")  # suffix alone (non-'0' ending)
    assert is_preferred("005930우", "삼성전자우")  # name alone
    assert not is_preferred("005930", "삼성전자")


def test_spac_and_reit_by_name():
    assert is_spac("유안타제12호스팩")
    assert not is_spac("삼성전자")
    assert is_reit("롯데리츠")
    assert not is_reit("삼성전자")


def test_common_stock_excludes_all_special_types():
    assert is_common_stock("005930", "삼성전자", etf_etn=ETF)
    assert not is_common_stock("005935", "삼성전자우", etf_etn=ETF)  # preferred
    assert not is_common_stock("349070", "유안타제12호스팩", etf_etn=ETF)  # spac
    assert not is_common_stock("330590", "롯데리츠", etf_etn=ETF)  # reit
    assert not is_common_stock("069500", "KODEX 200", etf_etn=ETF)  # etf
