# Changelog

All notable changes to MOMARAB CORE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-02-28

### Added
- **Initial Release** of MOMARAB CORE WordPress plugin
- **Custom Post Type**: `games` with comprehensive meta fields
- **Four Taxonomies**: 
  - `game_type` (أنواع الألعاب)
  - `game_status` (حالة اللعبة) 
  - `game_mode` (أسلوب اللعب)
  - `game_platform` (المنصات)
- **Advanced Rating System**: 
  - Story, Gameplay, Graphics, Audio ratings (1-10 scale)
  - Overall rating with notes support
  - Visual rating displays and progress bars
- **Meta Fields System**:
  - Basic info (developer, publisher, release date, official site)
  - Engine selection (Unreal Engine, Unity, CryEngine, Frostbite, Custom)
  - Features (up to 4 key features)
  - Media (2 YouTube videos, gallery up to 4 images)
- **Ajax Filtering**:
  - Real-time filtering by taxonomies and sorting
  - URL updates without page reload
  - Pagination support
  - Loading states and error handling
- **Shortcodes**:
  - `[momarab_games]` - Display games with filtering options
  - `[momarab_game_filter]` - Ajax filter interface
- **Widgets**:
  - Popular Games widget (sorted by rating)
  - Recent Games widget (sorted by date)
- **Related Posts Feature**:
  - Link posts to games via Select2 interface
  - Display latest related news on game pages
  - Configurable section title and enable/disable
- **REST API**:
  - `/wp-json/momarab/v1/games` endpoint
  - `/wp-json/momarab/v1/taxonomies` endpoint
  - Read-only access with CORS support
  - Parameter validation and sanitization
  - 50 items per page limit enforced
- **Templates System**:
  - `single-games.php` - Individual game display
  - `archive-games.php` - Games archive with filtering
  - Template parts for modular design
  - Theme override support
- **Internationalization (i18n)**:
  - Full Arabic translation support
  - RTL (Right-to-Left) layout support
  - Text domain: `momarab-core`
  - JavaScript translation support
- **Performance Optimization**:
  - Smart caching system (10-minute transients)
  - Cache invalidation on content changes
  - Lazy loading for images
  - Conditional asset loading
  - Custom image sizes (mcp-card, mcp-thumb, mcp-hero)
- **Security Features**:
  - Nonce verification for all forms
  - Data sanitization and validation
  - Capability checks for user permissions
  - XSS protection in templates
- **Blocksy Theme Integration**:
  - CSS inheritance from theme
  - No CSS reset - respects theme styles
  - All classes prefixed with `mcp-`
  - Theme color and font variables support
- **Admin Interface**:
  - Comprehensive meta boxes for game editing
  - Settings page with terms management tools
  - Dashboard widget with statistics
  - Select2 integration for game selection
  - Form validation and error handling
- **Assets Management**:
  - Responsive CSS for all screen sizes
  - Modern JavaScript with ES6+ features
  - Admin-specific styles and scripts
  - Frontend interaction enhancements

### Technical Details
- **WordPress Requirements**: 6.0+
- **PHP Requirements**: 7.4+ (tested up to 8.3)
- **Namespace**: `Momarab_Core`
- **Database**: Uses WordPress native tables with meta fields
- **Autoloading**: PSR-4 compatible autoloader
- **Code Standards**: WordPress Coding Standards compliant

### Security
- All user inputs sanitized using WordPress functions
- Nonce verification for all form submissions
- Capability checks for administrative functions
- Template output escaped to prevent XSS
- CORS headers configured for read-only API access

### Performance
- Transient caching for expensive queries
- Conditional script/style loading
- Image optimization with custom sizes
- Database query optimization
- 50-item pagination limit enforced

### Accessibility
- ARIA labels for interactive elements
- Keyboard navigation support
- Screen reader compatible
- High contrast support
- Semantic HTML structure

---

## Future Releases

### Planned for v1.1.0
- [ ] Advanced search functionality
- [ ] Game comparison feature
- [ ] User reviews and ratings
- [ ] Social sharing integration
- [ ] Enhanced gallery with lightbox
- [ ] Import/export functionality

### Planned for v1.2.0
- [ ] Multi-language support beyond Arabic
- [ ] Advanced filtering options
- [ ] Game recommendation engine
- [ ] Integration with gaming APIs
- [ ] Advanced analytics and reporting

---

## Support and Contributing

- **GitHub Repository**: https://github.com/momarabdev/momarab-core
- **Documentation**: https://docs.momarab.com
- **Support Forum**: https://momarab.com/support
- **Bug Reports**: https://github.com/momarabdev/momarab-core/issues

## License

This project is licensed under the GPLv2 or later - see the [LICENSE](LICENSE) file for details.

---

*For more detailed information about each feature, please refer to the [README.md](README.md) file.*
