# SPEC.md - Web Colegio Horizon

## 1. Project Overview

- **Nombre**: Colegio Horizon - Sitio web institucional
- **Tipo**: Webapp fullstack (FastAPI + Next.js)
- **Funcionalidad**: Presentar información de la escuela, carreras, noticias, galería, y formulario de contacto
- **Usuario objetivo**: Padres, estudiantes, público general

## 2. UI/UX Specification

### Layout Structure
- **Header**: Logo + navegación + botón "Admisiones"
- **Hero**: Imagen grande con eslogan y CTA
- **Secciones**: Información institucional, Carreras, Noticias, Galería, Contacto
- **Footer**: Links, redes sociales, copyright

### Responsive Breakpoints
- Mobile: < 768px
- Tablet: 768px - 1024px
- Desktop: > 1024px

### Visual Design

#### Color Palette
- **Primary**: `#1E3A5F` (azul marino institucional)
- **Secondary**: `#F4A261` (dorado/arena - acento)
- **Background**: `#FAFBFC` (blanco hueso)
- **Text**: `#2D3748` (gris oscuro)
- **Accent**: `#2A9D8F` (verde esmeralda)

#### Typography
- **Headings**: "Playfair Display" (serif, elegante)
- **Body**: "Source Sans 3" (sans-serif, legible)
- **Sizes**: H1: 48px, H2: 36px, H3: 24px, Body: 16px

#### Spacing
- Base: 8px grid
- Section padding: 80px vertical
- Container max-width: 1200px

#### Visual Effects
- Sombras suaves en cards: `0 4px 20px rgba(0,0,0,0.08)`
- Transiciones: 0.3s ease
- Hover en botones: slight lift + shadow increase

### Components
1. **Navbar**: Sticky, cambia color al hacer scroll
2. **Hero**: Full-width con overlay oscuro y texto centrado
3. **Cards**: Para carreras y noticias (imagen + título + descripción + botón)
4. **Formulario**: Campos nombre, email, teléfono, mensaje
5. **Galería**: Grid de imágenes con lightbox
6. **Footer**: 3 columnas (acerca de, enlaces rápidos, contacto)

## 3. Functionality Specification

### Páginas
1. **Home** (`/`): Hero + información general + carrusel noticias + CTA final
2. **Nosotros** (`/nosotros`): Historia, misión, visión, valores
3. **Carreras** (`/carreras`): Lista de carreras con información detallada
4. **Noticias** (`/noticias`): Blog de noticias y eventos
5. **Contacto** (`/contacto`): Formulario de contacto

### API Endpoints (FastAPI)
- `GET /api/noticias` - Listar noticias
- `GET /api/carreras` - Listar carreras
- `POST /api/contacto` - Enviar mensaje de contacto

### Datos (inventados)
- **Nombre**: Colegio Horizon
- **Lema**: "Formando líderes del mañana"
- **Carreras**: Ingeniería en Sistemas, Administración, Contabilidad, Derecho, Medicina
- **Noticias**: 3-4 noticias de ejemplo

## 4. Acceptance Criteria
- [ ] El sitio carga sin errores
- [ ] Navegación funciona entre todas las páginas
- [ ] Formulario de contacto envía datos al API
- [ ] Diseño es responsive en móvil
- [ ] Imágenes y tipografías cargan correctamente
- [ ] Animaciones suaves al hacer scroll