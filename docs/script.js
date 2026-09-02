const observed = document.querySelectorAll('.cards article, .feature-list > div, .cta > div');
observed.forEach((el) => el.classList.add('reveal'));
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) entry.target.classList.add('visible');
  });
}, { threshold: 0.15 });
observed.forEach((el) => observer.observe(el));

const style = document.createElement('style');
style.textContent = '.reveal{opacity:0;transform:translateY(18px);transition:opacity .65s ease,transform .65s ease}.reveal.visible{opacity:1;transform:none}';
document.head.appendChild(style);
