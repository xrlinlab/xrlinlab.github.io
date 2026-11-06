(() => {
  const carousel = document.querySelector('.publication-carousel');
  if (!carousel) return;
  const track = carousel.querySelector('.featured-publications');
  const slides = [...track.querySelectorAll('.featured-publication')];
  if (slides.length < 2) return;

  const controls = carousel.querySelector('.publication-carousel-controls');
  const dots = document.createElement('div');
  dots.className = 'publication-carousel-dots';
  dots.setAttribute('role', 'group');
  dots.setAttribute('aria-label', 'Choose a selected publication');
  const makeButton = (label, text, action) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-label', label);
    button.textContent = text;
    button.addEventListener('click', action);
    return button;
  };
  let active = 0;
  let timer;
  let settling;
  let rotating = true;
  let hovered = false;
  let focused = false;
  let touching = false;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const counter = document.createElement('span');
  counter.className = 'publication-carousel-counter';
  counter.setAttribute('aria-live', 'off');
  const rotation = makeButton('Pause automatic rotation', 'Pause', () => {
    rotating = !rotating;
    if (rotating) { hovered = false; focused = false; }
    rotation.textContent = rotating ? 'Pause' : 'Play';
    rotation.setAttribute('aria-label', rotating ? 'Pause automatic rotation' : 'Start automatic rotation');
    restart();
  });
  rotation.className = 'publication-carousel-rotation';

  const restart = () => {
    window.clearInterval(timer);
    if (rotating && !hovered && !focused && !touching && !document.hidden) {
      timer = window.setInterval(() => goTo(active + 1, false), 5000);
    }
    track.setAttribute('aria-live', rotating && !hovered && !focused && !touching && !document.hidden ? 'off' : 'polite');
  };
  const update = () => {
    counter.textContent = `${active + 1} / ${slides.length}`;
    slides.forEach((slide, index) => {
      slide.inert = index !== active;
      slide.setAttribute('aria-hidden', index === active ? 'false' : 'true');
      dotButtons[index].setAttribute('aria-current', index === active ? 'true' : 'false');
    });
  };
  const goTo = (index, manual = true, animate = true) => {
    window.clearTimeout(settling);
    active = (index + slides.length) % slides.length;
    const left = track.scrollLeft + slides[active].getBoundingClientRect().left - track.getBoundingClientRect().left;
    track.scrollTo({left, behavior: animate && !reducedMotion.matches ? 'smooth' : 'instant'});
    update();
    if (manual) restart();
  };
  const previous = makeButton('Previous selected publication', '←', () => goTo(active - 1));
  const next = makeButton('Next selected publication', '→', () => goTo(active + 1));
  controls.append(previous, counter, next, rotation);
  const dotButtons = slides.map((slide, index) => {
    slide.setAttribute('role', 'group');
    slide.setAttribute('aria-roledescription', 'slide');
    slide.setAttribute('aria-label', `${index + 1} of ${slides.length}`);
    const title = slide.querySelector('.feature-copy > div:nth-child(2)').textContent.trim();
    const button = makeButton(`Show selected publication ${index + 1}: ${title}`, '', () => goTo(index));
    dots.appendChild(button);
    return button;
  });
  carousel.appendChild(dots);
  controls.hidden = false;
  update();
  restart();

  track.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const destinations = {ArrowLeft: active - 1, ArrowRight: active + 1, Home: 0, End: slides.length - 1};
    if (!(event.key in destinations)) return;
    event.preventDefault();
    goTo(destinations[event.key]);
  });
  track.addEventListener('scroll', () => {
    window.clearTimeout(settling);
    settling = window.setTimeout(() => {
      const left = track.getBoundingClientRect().left;
      active = slides.reduce((best, slide, index) => Math.abs(slide.getBoundingClientRect().left - left) < Math.abs(slides[best].getBoundingClientRect().left - left) ? index : best, 0);
      update();
    }, 120);
  }, {passive: true});
  carousel.addEventListener('mouseenter', () => { hovered = true; restart(); });
  carousel.addEventListener('mouseleave', () => { hovered = false; restart(); });
  carousel.addEventListener('focusin', () => { focused = true; restart(); });
  carousel.addEventListener('focusout', (event) => {
    if (!carousel.contains(event.relatedTarget)) { focused = false; restart(); }
  });
  document.addEventListener('visibilitychange', restart);
  carousel.addEventListener('pointerdown', (event) => {
    if (event.pointerType === 'touch') { touching = true; restart(); }
  });
  ['pointerup', 'pointercancel'].forEach((name) => carousel.addEventListener(name, () => { touching = false; restart(); }));
  window.addEventListener('resize', () => goTo(active, false, false));
})();
