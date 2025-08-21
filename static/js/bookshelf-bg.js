// Animated bookshelf SVG background with side accents

// Main background bookshelf
const svg = document.getElementById('animated-bookshelf');
if (svg) {
  const shelves = 5;
  const booksPerShelf = 12;
  const shelfHeight = 120;
  const bookMin = 28, bookMax = 54;
  const colors = [
    'var(--book1)', 'var(--book2)', 'var(--book3)', 'var(--book4)', 'var(--book5)'
  ];

  svg.setAttribute('viewBox', `0 0 1200 700`);
  svg.innerHTML = '';

  // Draw shelves
  for (let s = 0; s < shelves; ++s) {
    const y = 80 + s * shelfHeight;
    // Shelf bar
    const shelf = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    shelf.setAttribute('x', 60);
    shelf.setAttribute('y', y + 48);
    shelf.setAttribute('width', 1080);
    shelf.setAttribute('height', 18);
    shelf.setAttribute('rx', 7);
    shelf.setAttribute('fill', 'var(--shelf)');
    shelf.setAttribute('opacity', '0.95');
    svg.appendChild(shelf);

    // Books
    let x = 80;
    for (let b = 0; b < booksPerShelf; ++b) {
      const w = bookMin + Math.random() * (bookMax - bookMin);
      const h = 60 + Math.random() * 38;
      const book = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      book.setAttribute('x', x);
      book.setAttribute('y', y + 48 - h);
      book.setAttribute('width', w);
      book.setAttribute('height', h);
      book.setAttribute('rx', 5 + Math.random() * 4);
      book.setAttribute('fill', colors[Math.floor(Math.random() * colors.length)]);
      book.setAttribute('opacity', 0.82 + Math.random() * 0.16);
      svg.appendChild(book);

      // Animate books up/down slightly
      const anim = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
      anim.setAttribute('attributeName', 'transform');
      anim.setAttribute('type', 'translate');
      anim.setAttribute('values', `0,0; 0,${-4 - Math.random()*3}; 0,0`);
      anim.setAttribute('dur', `${2.5 + Math.random()*2}s`);
      anim.setAttribute('repeatCount', 'indefinite');
      anim.setAttribute('begin', `${Math.random()*2}s`);
      book.appendChild(anim);

      x += w + 12 + Math.random() * 10;
      if (x > 1100) break;
    }
  }
}

// Side bookshelf accents
function drawSideBookshelf(svg, flip = false) {
  if (!svg) return;
  svg.innerHTML = '';
  const shelfCount = 6;
  const shelfGap = 140;
  const bookColors = [
    'var(--book1)', 'var(--book2)', 'var(--book3)', 'var(--book4)', 'var(--book5)'
  ];
  for (let s = 0; s < shelfCount; ++s) {
    const y = 40 + s * shelfGap;
    // Shelf
    const shelf = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    shelf.setAttribute('x', 10);
    shelf.setAttribute('y', y + 48);
    shelf.setAttribute('width', 100);
    shelf.setAttribute('height', 14);
    shelf.setAttribute('rx', 6);
    shelf.setAttribute('fill', 'var(--shelf)');
    shelf.setAttribute('opacity', '0.93');
    svg.appendChild(shelf);

    // Books
    let x = 18;
    const books = 4 + Math.floor(Math.random() * 3);
    for (let b = 0; b < books; ++b) {
      const w = 14 + Math.random() * 18;
      const h = 38 + Math.random() * 32;
      const book = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      book.setAttribute('x', x);
      book.setAttribute('y', y + 48 - h);
      book.setAttribute('width', w);
      book.setAttribute('height', h);
      book.setAttribute('rx', 3 + Math.random() * 2);
      book.setAttribute('fill', bookColors[Math.floor(Math.random() * bookColors.length)]);
      book.setAttribute('opacity', 0.82 + Math.random() * 0.16);
      svg.appendChild(book);

      // Animate books up/down slightly
      const anim = document.createElementNS('http://www.w3.org/2000/svg', 'animateTransform');
      anim.setAttribute('attributeName', 'transform');
      anim.setAttribute('type', 'translate');
      anim.setAttribute('values', `0,0; 0,${-2 - Math.random()*2}; 0,0`);
      anim.setAttribute('dur', `${2.5 + Math.random()*2}s`);
      anim.setAttribute('repeatCount', 'indefinite');
      anim.setAttribute('begin', `${Math.random()*2}s`);
      book.appendChild(anim);

      x += w + 6 + Math.random() * 6;
      if (x > 90) break;
    }
  }
}
drawSideBookshelf(document.querySelector('.bookshelf-side.left'));
drawSideBookshelf(document.querySelector('.bookshelf-side.right'), true);