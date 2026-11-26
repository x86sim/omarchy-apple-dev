// The scene life cycle for apps whose windowing library still makes its windows the pre-iOS 13 way
// (-[UIWindow initWithFrame:] + makeKeyAndVisible, as winit 0.30 does): iOS 27 launches an app built with its SDK only
// when it adopts scenes, and a window that belongs to no scene is never shown.
//
// rust/build.py links this object into such an app and names RustSceneAdapter as the scene delegate in the Info.plist.
// Windows made before the scene connects are attached to it when it does; windows made later join it at once.
// The library's own lifecycle keeps working: UIKit still posts the UIApplication notifications (did become active, ...)
// that winit observes, and the scene's activation callbacks are passed on to the app delegate's
// applicationDidBecomeActive: & co., which UIKit no longer calls under scenes (tao before 0.37 waits for those).
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

static NSHashTable<UIWindow *> *rsa_waiting;
static __weak UIWindowScene *rsa_scene;

@interface RustSceneAdapter : UIResponder <UIWindowSceneDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

@interface UIWindow (RustSceneAdapter)
- (instancetype)rsa_initWithFrame:(CGRect)frame;
@end

@implementation UIWindow (RustSceneAdapter)
- (instancetype)rsa_initWithFrame:(CGRect)frame {
  UIWindow *w = [self rsa_initWithFrame:frame];  // the original -initWithFrame: (exchanged in +load)
  if (w && !w.windowScene) {
    UIWindowScene *scene = rsa_scene;
    if (scene) {
      w.windowScene = scene;
    } else {
      [rsa_waiting addObject:w];
    }
  }
  return w;
}
@end

@implementation RustSceneAdapter

+ (void)load {
  rsa_waiting = [NSHashTable weakObjectsHashTable];
  Method original = class_getInstanceMethod([UIWindow class], @selector(initWithFrame:));
  Method adapter = class_getInstanceMethod([UIWindow class], @selector(rsa_initWithFrame:));
  method_exchangeImplementations(original, adapter);
}

- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
  if (![scene isKindOfClass:[UIWindowScene class]]) {
    return;
  }
  UIWindowScene *ws = (UIWindowScene *)scene;
  rsa_scene = ws;
  for (UIWindow *w in rsa_waiting.allObjects) {
    w.windowScene = ws;
    if (!self.window) {
      self.window = w;
    }
    [w makeKeyAndVisible];
  }
  [rsa_waiting removeAllObjects];
}

static void rsa_forward(SEL sel) {
  UIApplication *app = UIApplication.sharedApplication;
  id<UIApplicationDelegate> d = app.delegate;
  if ([d respondsToSelector:sel]) {
    ((void (*)(id, SEL, UIApplication *))[(NSObject *)d methodForSelector:sel])(d, sel, app);
  }
}

- (void)sceneDidBecomeActive:(UIScene *)scene {
  rsa_forward(@selector(applicationDidBecomeActive:));
}

- (void)sceneWillResignActive:(UIScene *)scene {
  rsa_forward(@selector(applicationWillResignActive:));
}

- (void)sceneWillEnterForeground:(UIScene *)scene {
  rsa_forward(@selector(applicationWillEnterForeground:));
}

- (void)sceneDidEnterBackground:(UIScene *)scene {
  rsa_forward(@selector(applicationDidEnterBackground:));
}

- (void)sceneDidDisconnect:(UIScene *)scene {
  if (scene == rsa_scene) {
    rsa_scene = nil;
  }
}

@end
