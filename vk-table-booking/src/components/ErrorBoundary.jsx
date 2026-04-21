/**
 * Глобальный ErrorBoundary — ловит ошибки рендера React.
 * Оборачивает <App /> в main.jsx.
 * При ошибке отправляет отчёт на /api/error-report и показывает
 * дружественный экран вместо белой страницы.
 */

import { Component } from 'react';
import { Placeholder, Button } from '@vkontakte/vkui';

class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error, info) {
        fetch('/api/error-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `React Error: ${error.message}`,
                details: info.componentStack,
                source: 'frontend',
            }),
        }).catch(() => {});
    }

    render() {
        if (this.state.hasError) {
            return (
                <Placeholder
                    header="Что-то пошло не так"
                    action={
                        <Button
                            size="l"
                            onClick={() => this.setState({ hasError: false })}
                        >
                            Попробовать снова
                        </Button>
                    }
                >
                    Произошла неожиданная ошибка. Пожалуйста, попробуйте ещё раз.
                </Placeholder>
            );
        }
        return this.props.children;
    }
}

export default ErrorBoundary;
