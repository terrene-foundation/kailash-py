// Custom JavaScript for Kailash SDK Documentation

document.addEventListener('DOMContentLoaded', function() {
    // Add copy buttons to code blocks (backup for sphinx-copybutton)
    const codeBlocks = document.querySelectorAll('pre');

    codeBlocks.forEach(block => {
        // Skip if copy button already exists
        if (block.querySelector('.copy-button')) return;

        const button = document.createElement('button');
        button.className = 'copy-button';
        button.textContent = 'Copy';
        button.style.position = 'absolute';
        button.style.top = '5px';
        button.style.right = '5px';
        button.style.padding = '3px 8px';
        button.style.fontSize = '12px';
        button.style.border = '1px solid #ddd';
        button.style.borderRadius = '3px';
        button.style.background = '#fff';
        button.style.cursor = 'pointer';

        block.style.position = 'relative';
        block.appendChild(button);

        button.addEventListener('click', function() {
            const code = block.querySelector('code');
            const text = code ? code.textContent : block.textContent;

            navigator.clipboard.writeText(text).then(() => {
                button.textContent = 'Copied!';
                setTimeout(() => {
                    button.textContent = 'Copy';
                }, 2000);
            });
        });
    });

    // Improve navigation highlighting
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.wy-menu a');

    navLinks.forEach(link => {
        if (link.href.includes(currentPath)) {
            link.parentElement.classList.add('current');
        }
    });

    // Add anchor links to headers
    const headers = document.querySelectorAll('h1, h2, h3, h4, h5, h6');

    headers.forEach(header => {
        if (header.id) {
            const anchor = document.createElement('a');
            anchor.className = 'header-anchor';
            anchor.href = '#' + header.id;
            anchor.innerHTML = '¶';
            anchor.style.marginLeft = '10px';
            anchor.style.opacity = '0.5';
            anchor.style.textDecoration = 'none';

            header.appendChild(anchor);
        }
    });
});
