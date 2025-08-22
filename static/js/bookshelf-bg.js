// Animated bookshelf background (main grid + side accents)
(() => {
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const rand = (min, max) => min + Math.random() * (max - min);
  const randint = (min, max) => Math.floor(rand(min, max + 1));

  const COLORS = ['var(--book1)', 'var(--book2)', 'var(--book3)', 'var(--book4)', 'var(--book5)'];
  const SHELF_FILL = 'var(--shelf)';

  // Main bookshelf (center)
  const main = document.getElementById('animated-bookshelf');
  if (main) {
    const shelves = 6;
    const booksPerShelf = 18;
    const shelfHeight = 120;
    const top = 80;
    const barH = 18;
    const barX = 60;
    const barW = 1080;
    const viewW = 1200;
    const viewH = top + shelves * shelfHeight + 100;

    main.setAttribute('viewBox', `0 0 ${viewW} ${viewH}`);
    main.innerHTML = '';

    for (let s = 0; s < shelves; s++) {
      const y = top + s * shelfHeight;

      const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bar.setAttribute('x', barX);
      bar.setAttribute('y', (y + 48).toString());
      bar.setAttribute('width', barW.toString());
      bar.setAttribute('height', barH.toString());
      bar.setAttribute('rx', '7');
      bar.setAttribute('fill', SHELF_FILL);
      bar.setAttribute('opacity', '0.95');
      main.appendChild(bar);

      let x = 80;
      for (let b = 0; b < booksPerShelf; b++) {
        const w = rand(28, 54);
        const h = rand(60, 98);

        const book = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        book.setAttribute('x', x.toString());
        book.setAttribute('y', (y + 48 - h).toString());
        book.setAttribute('width', w.toString());
        book.setAttribute('height', h.toString());
        book.setAttribute('rx', rand(5, 9).toFixed(2));
        book.setAttribute('fill', pick(COLORS));
        book.setAttribute('opacity', (0.82 + Math.random() * 0.16).toFixed(2));
        main.appendChild(book);

        const anim = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
        anim.setAttribute('attributeName', 'transform');
        anim.setAttribute('type', 'translate');
        anim.setAttribute('values', `0,0; 0,${(-rand(2, 7)).toFixed(2)}; 0,0`);
        anim.setAttribute('dur', `${(2.5 + Math.random() * 2).toFixed(2)}s`);
        anim.setAttribute('repeatCount', 'indefinite');
        anim.setAttribute('begin', `${Math.random().toFixed(2)}s`);
        book.appendChild(anim);

        x += w + 12 + Math.random() * 10;
        if (x > 1100) break;
      }
    }
  }

  // Side bookshelves (left/right). If right is mirrored via CSS, no flip needed here.
  function drawSideBookshelf(svg) {
    if (!svg) return;
    svg.innerHTML = '';

    const shelfCount = 8;
    const shelfGap = 100;

    for (let s = 0; s < shelfCount; s++) {
      const y = 40 + s * shelfGap;

      const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bar.setAttribute('x', '10');
      bar.setAttribute('y', (y + 48).toString());
      bar.setAttribute('width', '100');
      bar.setAttribute('height', '14');
      bar.setAttribute('rx', '6');
      bar.setAttribute('fill', SHELF_FILL);
      bar.setAttribute('opacity', '0.93');
      svg.appendChild(bar);

      let x = 18;
      const books = randint(7, 9);
      for (let b = 0; b < books; b++) {
        const w = rand(14, 32);
        const h = rand(38, 70);

        const book = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        book.setAttribute('x', x.toString());
        book.setAttribute('y', (y + 48 - h).toString());
        book.setAttribute('width', w.toString());
        book.setAttribute('height', h.toString());
        book.setAttribute('rx', rand(3, 5).toFixed(2));
        book.setAttribute('fill', pick(COLORS));
        book.setAttribute('opacity', (0.82 + Math.random() * 0.16).toFixed(2));
        svg.appendChild(book);

        const anim = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
        anim.setAttribute('attributeName', 'transform');
        anim.setAttribute('type', 'translate');
        anim.setAttribute('values', `0,0; 0,${(-rand(2, 4)).toFixed(2)}; 0,0`);
        anim.setAttribute('dur', `${(2.5 + Math.random() * 2).toFixed(2)}s`);
        anim.setAttribute('repeatCount', 'indefinite');
        anim.setAttribute('begin', `${Math.random().toFixed(2)}s`);
        book.appendChild(anim);

        x += w + 6 + Math.random() * 6;
        if (x > 90) break;
      }
    }
  }

  drawSideBookshelf(document.querySelector('.bookshelf-side.left'));
  drawSideBookshelf(document.querySelector('.bookshelf-side.right'));
})();
