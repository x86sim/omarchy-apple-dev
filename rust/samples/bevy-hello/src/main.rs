//! A Bevy app built on Linux with rust/build.py: a title and a tap counter, drawn by wgpu on Metal.
//! It has no accessibility tree; x86Sim's snapshot reads its text by OCR.
use bevy::prelude::*;
use bevy::text::FontSize;
use bevy::window::{MonitorSelection, WindowMode};

#[derive(Component)]
struct Counter;

fn main() {
    App::new()
        .insert_resource(ClearColor(Color::srgb(0.08, 0.09, 0.12)))
        // the whole screen: winit on iOS takes the requested size as the window's frame (Bevy's default is 1280x720)
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                mode: WindowMode::BorderlessFullscreen(MonitorSelection::Primary),
                ..default()
            }),
            ..default()
        }))
        .add_systems(Startup, setup)
        .add_systems(Update, count_taps)
        .run();
}

fn setup(mut commands: Commands) {
    commands.spawn(Camera2d);
    commands
        .spawn(Node {
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            row_gap: px(40),
            ..default()
        })
        .with_children(|p| {
            p.spawn((Text::new("Bevy on x86Sim"), TextFont { font_size: FontSize::Px(44.0), ..default() }, TextColor(Color::WHITE)));
            p.spawn((Text::new("Taps: 0"), TextFont { font_size: FontSize::Px(40.0), ..default() }, TextColor(Color::srgb(1.0, 0.8, 0.3)), Counter));
        });
}

fn count_taps(
    touches: Res<Touches>,
    mouse: Res<ButtonInput<MouseButton>>,
    mut taps: Local<u32>,
    mut q: Query<&mut Text, With<Counter>>,
) {
    if touches.any_just_pressed() || mouse.just_pressed(MouseButton::Left) {
        *taps += 1;
        for mut t in &mut q {
            t.0 = format!("Taps: {}", *taps);
        }
    }
}
