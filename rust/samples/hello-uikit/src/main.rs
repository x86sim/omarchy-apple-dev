//! A UIKit app written only in Rust (objc2): a label and a button that counts its taps.
//! Built on Linux with rust/build.sh; the smallest check that cargo, the Darwin SDK and ld64.lld make a working app.
//! iOS 27 runs apps built with its SDK only with the scene life cycle: the window comes from a UIWindowSceneDelegate
//! (RustHelloSceneDelegate, named in the Info.plist's UIApplicationSceneManifest: [package.metadata.ios] in Cargo.toml).
use std::cell::{Cell, RefCell};

use objc2::rc::Retained;
use objc2::runtime::{AnyObject, NSObjectProtocol};
use objc2::{define_class, sel, ClassType, MainThreadMarker, MainThreadOnly};
use objc2_core_foundation::{CGPoint, CGRect, CGSize};
use objc2_foundation::{NSDictionary, NSString};
use objc2_ui_kit::{
    NSTextAlignment, UIApplication, UIApplicationDelegate, UIButton, UIButtonType, UIColor, UIControlEvents,
    UIControlState, UIFont, UILabel, UIResponder, UIScene, UISceneConnectionOptions, UISceneDelegate, UISceneSession,
    UIViewController, UIWindow, UIWindowScene, UIWindowSceneDelegate,
};

thread_local! {
    static WINDOW: RefCell<Option<Retained<UIWindow>>> = const { RefCell::new(None) };
    static LABEL: RefCell<Option<Retained<UILabel>>> = const { RefCell::new(None) };
    static TAPS: Cell<u32> = const { Cell::new(0) };
}

fn rect(x: f64, y: f64, w: f64, h: f64) -> CGRect {
    CGRect::new(CGPoint::new(x, y), CGSize::new(w, h))
}

define_class!(
    #[unsafe(super(UIResponder))]
    #[name = "RustHelloAppDelegate"]
    #[thread_kind = MainThreadOnly]
    struct AppDelegate;

    unsafe impl NSObjectProtocol for AppDelegate {}

    unsafe impl UIApplicationDelegate for AppDelegate {
        #[unsafe(method(application:didFinishLaunchingWithOptions:))]
        fn did_finish_launching(&self, _app: &UIApplication, _options: Option<&NSDictionary>) -> bool {
            true
        }
    }
);

define_class!(
    #[unsafe(super(UIResponder))]
    #[name = "RustHelloSceneDelegate"]
    #[thread_kind = MainThreadOnly]
    struct SceneDelegate;

    unsafe impl NSObjectProtocol for SceneDelegate {}

    unsafe impl UISceneDelegate for SceneDelegate {
        #[unsafe(method(scene:willConnectToSession:options:))]
        fn will_connect(&self, scene: &UIScene, _session: &UISceneSession, _options: &UISceneConnectionOptions) {
            let mtm = MainThreadMarker::from(self);
            let Some(scene) = scene.downcast_ref::<UIWindowScene>() else { return };
            let window = UIWindow::initWithWindowScene(UIWindow::alloc(mtm), scene);
            let bounds = window.bounds();
            let vc = UIViewController::new(mtm);
            let view = vc.view().expect("a view");
            view.setBackgroundColor(Some(&UIColor::systemBackgroundColor()));

            let w = bounds.size.width;
            let title = UILabel::initWithFrame(UILabel::alloc(mtm), rect(20.0, 160.0, w - 40.0, 40.0));
            title.setText(Some(&NSString::from_str("Hello from Rust")));
            unsafe { title.setFont(Some(&UIFont::boldSystemFontOfSize(28.0))) };
            title.setTextAlignment(NSTextAlignment::Center);
            view.addSubview(&title);

            let label = UILabel::initWithFrame(UILabel::alloc(mtm), rect(20.0, 220.0, w - 40.0, 30.0));
            label.setText(Some(&NSString::from_str("Taps: 0")));
            label.setTextAlignment(NSTextAlignment::Center);
            view.addSubview(&label);

            let button = UIButton::buttonWithType(UIButtonType::System, mtm);
            button.setFrame(rect(w / 2.0 - 80.0, 270.0, 160.0, 44.0));
            unsafe {
                button.setTitle_forState(Some(&NSString::from_str("Tap me")), UIControlState::Normal);
                button.addTarget_action_forControlEvents(Some(self), sel!(tapped:), UIControlEvents::TouchUpInside);
            }
            view.addSubview(&button);

            window.setRootViewController(Some(&vc));
            window.makeKeyAndVisible();
            WINDOW.with(|c| *c.borrow_mut() = Some(window));
            LABEL.with(|c| *c.borrow_mut() = Some(label));
        }
    }

    unsafe impl UIWindowSceneDelegate for SceneDelegate {}

    impl SceneDelegate {
        #[unsafe(method(tapped:))]
        fn tapped(&self, _sender: Option<&AnyObject>) {
            let n = TAPS.with(|t| {
                t.set(t.get() + 1);
                t.get()
            });
            println!("tapped {n}");
            LABEL.with(|c| {
                if let Some(l) = c.borrow().as_ref() {
                    l.setText(Some(&NSString::from_str(&format!("Taps: {n}"))));
                }
            });
        }
    }
);

fn main() {
    let mtm = MainThreadMarker::new().expect("main thread");
    let name = NSString::from_str("RustHelloAppDelegate");
    // registers the classes before UIKit looks them up by name
    let _ = (AppDelegate::class(), SceneDelegate::class());
    UIApplication::main(None, Some(&name), mtm);
}
