"""Infrastructure 공통 예외."""


class ConfigError(Exception):
    """필수 설정 값이 비어 있을 때 발생합니다."""


class DBConnectionError(Exception):
    """DB 접속 실패 (Pritunl VPN 미연결, 인증 실패, timeout 등)."""

    USER_MESSAGE = (
        "현재 Pritunl VPN 또는 DB 연결 상태를 확인할 수 없습니다.\n"
        "DB 연결을 확인한 후 다시 시도해주세요."
    )
