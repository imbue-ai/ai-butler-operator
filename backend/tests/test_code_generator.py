from app.services.code_generator import CodeGenerator


def test_generate_returns_6_digit_string(code_generator: CodeGenerator):
    code = code_generator.generate()
    assert len(code) == 6
    assert code.isdigit()


def test_generate_returns_unique_codes(code_generator: CodeGenerator):
    codes = {code_generator.generate() for _ in range(50)}
    assert len(codes) == 50


def test_is_active(code_generator: CodeGenerator):
    code = code_generator.generate()
    assert code_generator.is_active(code) is True
    assert code_generator.is_active("999999") is False


def test_release(code_generator: CodeGenerator):
    code = code_generator.generate()
    assert code_generator.is_active(code) is True
    code_generator.release(code)
    assert code_generator.is_active(code) is False


def test_active_count(code_generator: CodeGenerator):
    assert code_generator.active_count == 0
    code_generator.generate()
    code_generator.generate()
    assert code_generator.active_count == 2


def test_release_nonexistent_does_not_raise(code_generator: CodeGenerator):
    code_generator.release("000000")  # Should not raise
