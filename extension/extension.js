// hey-claude top-bar indicator. Deliberately dumb: every action is one D-Bus
// call to the heyclauded daemon, every visual is driven by its signals.
// All logic lives in the daemon (see PLAN.md ground rules).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const BUS_NAME = 'org.kdc.HeyClaude';
const OBJECT_PATH = '/org/kdc/HeyClaude';

const HeyClaudeIface = `
<node>
  <interface name="org.kdc.HeyClaude">
    <method name="Toggle"/>
    <method name="StartListening"/>
    <method name="StopListening"/>
    <method name="Cancel"/>
    <method name="NewConversation"/>
    <method name="Ask"><arg type="s" direction="in" name="text"/></method>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="state"/></signal>
    <signal name="Transcript"><arg type="s" name="who"/><arg type="s" name="text"/></signal>
    <property name="State" type="s" access="read"/>
    <property name="SessionId" type="s" access="read"/>
  </interface>
</node>`;

const HeyClaudeProxy = Gio.DBusProxy.makeProxyWrapper(HeyClaudeIface);

const STATE_ICONS = {
    idle: 'audio-input-microphone-symbolic',
    recording: 'media-record-symbolic',
    transcribing: 'document-edit-symbolic',
    thinking: 'emblem-synchronizing-symbolic',
    speaking: 'audio-volume-high-symbolic',
};

const Indicator = GObject.registerClass(
class HeyClaudeIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.5, 'hey-claude');

        this._icon = new St.Icon({
            icon_name: STATE_ICONS.idle,
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this._youItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._claudeItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._youItem.visible = this._claudeItem.visible = false;
        this.menu.addMenuItem(this._youItem);
        this.menu.addMenuItem(this._claudeItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction('New conversation', () => this._call('NewConversation'));
        this.menu.addAction('Cancel', () => this._call('Cancel'));
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction('Edit configuration', () => this._openConfig());
        this.menu.addAction('Quit daemon', () => this._call('Quit'));

        this._proxy = new HeyClaudeProxy(
            Gio.DBus.session, BUS_NAME, OBJECT_PATH,
            (_proxy, error) => {
                if (!error)
                    this._setState(this._proxy.State ?? 'idle');
            },
            null,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START_AT_CONSTRUCTION);
        this._stateChangedId = this._proxy.connectSignal('StateChanged',
            (_p, _sender, [state]) => this._setState(state));
        this._transcriptId = this._proxy.connectSignal('Transcript',
            (_p, _sender, [who, text]) => this._setTranscript(who, text));
        this._ownerId = this._proxy.connect('notify::g-name-owner', () => {
            if (!this._proxy.g_name_owner)
                this._setState('idle');
        });
    }

    toggle() {
        this._call('Toggle');
    }

    _call(name) {
        // method calls (re)activate the daemon via D-Bus activation
        this._proxy[`${name}Remote`](err => {
            if (err)
                Main.notify('hey-claude', `Daemon call failed: ${err.message}`);
        });
    }

    _setState(state) {
        this._icon.icon_name = STATE_ICONS[state] ?? STATE_ICONS.idle;
        this._icon.style_class = state === 'idle'
            ? 'system-status-icon'
            : `system-status-icon hc-${state}`;
    }

    _setTranscript(who, text) {
        const item = who === 'you' ? this._youItem : this._claudeItem;
        const label = who === 'you' ? 'You' : 'Claude';
        const short = text.length > 72 ? `${text.slice(0, 72)}…` : text;
        item.label.set_text(`${label}: ${short}`);
        item.visible = true;
        // replies also land as a notification so long answers survive
        // the spoken "the rest is on screen" truncation
        if (who === 'claude') {
            const body = text.length > 400 ? `${text.slice(0, 400)}…` : text;
            Main.notify('Claude', body);
        }
    }

    _openConfig() {
        const path = GLib.build_filenamev([GLib.get_user_config_dir(),
            'hey-claude', 'config.toml']);
        const file = Gio.File.new_for_path(path);
        if (!file.query_exists(null)) {
            Main.notify('hey-claude',
                `No config yet — copy config.example.toml from the repo to ${path}`);
            return;
        }
        Gio.AppInfo.launch_default_for_uri(file.get_uri(), null);
    }

    vfunc_event(event) {
        // primary click / tap = push-to-talk; anything else opens the menu
        if ((event.type() === Clutter.EventType.BUTTON_PRESS &&
             event.get_button() === Clutter.BUTTON_PRIMARY) ||
            event.type() === Clutter.EventType.TOUCH_BEGIN) {
            this.toggle();
            return Clutter.EVENT_STOP;
        }
        return super.vfunc_event(event);
    }

    destroy() {
        if (this._stateChangedId)
            this._proxy.disconnectSignal(this._stateChangedId);
        if (this._transcriptId)
            this._proxy.disconnectSignal(this._transcriptId);
        if (this._ownerId)
            this._proxy.disconnect(this._ownerId);
        this._proxy = null;
        super.destroy();
    }
});

export default class HeyClaudeExtension extends Extension {
    enable() {
        this._indicator = new Indicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        Main.wm.addKeybinding('toggle-shortcut', this.getSettings(),
            Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._indicator.toggle());
    }

    disable() {
        Main.wm.removeKeybinding('toggle-shortcut');
        this._indicator?.destroy();
        this._indicator = null;
    }
}
