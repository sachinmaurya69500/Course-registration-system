(() => {
    const html = document.documentElement;
    const themeToggle = document.getElementById('themeToggle');
    const storageKey = 'course-registration-theme';

    const applyTheme = (theme) => {
        html.setAttribute('data-bs-theme', theme);
        if (themeToggle) {
            themeToggle.innerHTML = theme === 'dark'
                ? '<i class="bi bi-sun"></i>'
                : '<i class="bi bi-moon-stars"></i>';
        }
    };

    const savedTheme = localStorage.getItem(storageKey) || 'light';
    applyTheme(savedTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const nextTheme = html.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
            localStorage.setItem(storageKey, nextTheme);
            applyTheme(nextTheme);
        });
    }
})();
