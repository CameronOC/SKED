# project/main/views.py

#################
#### imports ####
#################
import datetime

from flask import render_template, Blueprint, request, session, g, redirect, url_for, flash
from source import app, db, bcrypt
from flask_login import login_required, login_user, logout_user
from forms import CreateForm, InviteForm, JoinForm, PositionForm, ShiftForm

from models import User, Organization, Membership, Position, Shift
from decorators import check_confirmed

from token import generate_confirmation_token, confirm_token, generate_invitation_token, confirm_invitation_token

import datetime
from source.email import send_email
from source.decorators import check_confirmed

################
#    config    #
################

main_blueprint = Blueprint('main', __name__, )


@app.before_request
def load_user():
    if 'user_id' in session:
        if session["user_id"]:
            user = User.query.filter_by(id=session["user_id"]).first()
        else:
            user = {"email": "Guest"}  # Make it better, use an anonymous User instead
    else:
        user = None

    g.user = user


################
#    routes    #
################

@main_blueprint.route('/')
def landing():
    return render_template('main/index.html')


@main_blueprint.route('/home', methods=['GET', ])
@login_required
@check_confirmed
def home():
    orgs = g.user.orgs_owned.all()
    memberships = g.user.memberships.filter_by(is_owner=False).all()
    return render_template('main/home.html', organizations=orgs, memberships=memberships)


@main_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'GET':
        return render_template('main/create.html', form=CreateForm())
    else:
        name = request.form['name']

        org = Organization(name=name, owner=g.user)

        db.session.add(org)
        db.session.commit()

        membership = Membership(
            member=g.user,
            organization=org,
            is_owner=True,
            joined=True
        )
        db.session.add(membership)
        db.session.commit()

        return redirect('/organization/' + str(org.id))


@main_blueprint.route('/organization/<key>', methods=['GET', ])
@login_required
def organization(key):
    org = Organization.query.filter_by(id=key).first()

    if org.owner.id != g.user.id:
        return render_template('errors/403_organization_owner.html'), 403

    return render_template('main/organization.html', organization=org)

@main_blueprint.route('/organization/<orgKey>/position/<posKey>/shift/create', methods=['GET', 'POST'])
@login_required
def shift(orgKey, posKey):
    if request.method == 'GET':
        form = ShiftForm()
        memberships = Membership.query.filter_by(organization_id=orgKey).all()
        for c in memberships:
            form.user.choices.append((c.member.id, c.member.first_name+' '+c.member.last_name))
        return render_template('main/create_shift.html', form=form)
    else:
        assigned_user_id = request.form['user']
        day = request.form['day']
        start_time = datetime.datetime.strptime(request.form['start_time'], '%H:%M')
        end_time = datetime.datetime.strptime(request.form['end_time'], '%H:%M')
	
        shift = Shift(position_id=posKey, assigned_user_id=assigned_user_id, day=day, start_time=start_time, end_time=end_time)
	
        db.session.add(shift)
        db.session.commit()
	
        return redirect(url_for('main.position', key=orgKey, key2=posKey))

@main_blueprint.route('/organization/<key>/invite', methods=['GET', 'POST'])
@login_required
def invite(key):
    # get the organization to invite users to
    org = Organization.query.filter_by(id=key).first()
    form = InviteForm(request.form)
    if form.validate_on_submit():

        user = User.query.filter_by(email=form.email.data).first()

        if user is None:
            user = User(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                password="temp",
                confirmed=False
            )
            db.session.add(user)

        db.session.commit()

        membership = Membership.query.filter_by(member_id=user.id, organization_id=org.id).first()

        if membership is not None or user.id == org.owner.id:
            flash('This person is already a member of ' + org.name, 'danger')
            return render_template('main/invite.html', form=form, organization=org)

        membership = Membership(
            member=user,
            organization=org
        )
        db.session.add(membership)
        db.session.commit()

        token = generate_invitation_token(user.email)

        confirm_url = url_for('main.confirm_invite', key=org.id, token=token, _external=True)

        html = render_template('emails/invitation.html', confirm_url=confirm_url, user=user, organization=org)

        subject = "You've been invited to use SKEDD"

        send_email(user.email, subject, html)

        flash('You succesfully invited ' + user.first_name + ' ' + user.last_name + '.', 'success')

        # return redirect(url_for('user.unconfirmed'))

    return render_template('main/invite.html', form=form, organization=org)


@main_blueprint.route('/organization/<key>/join/<token>', methods=['GET', 'POST'])
def confirm_invite(key, token):
    try:
        email = confirm_token(token)
        user = User.query.filter_by(email=email).first_or_404()
        org = Organization.query.filter_by(id=key).first()
        membership = user.memberships.filter_by(organization_id=org.id).first_or_404()
        form = JoinForm(request.form)

        if user.confirmed:
            membership.joined = True
            db.session.commit()
            if g.user is None or g.user.id != user.id:
                login_user(user)
            flash('You have now joined ' + org.name, 'success')
            return redirect(url_for('main.home'))
        elif form.validate_on_submit():
            # will need error handling
            user.password = bcrypt.generate_password_hash(form.password.data)
            user.confirmed = True
            user.confirmed_on = datetime.datetime.now()
            membership.joined = True
            db.session.commit()
            if g.user is None or g.user.id != user.id:
                login_user(user)
            flash('You have now joined ' + org.name, 'success')
            return redirect(url_for('main.home'))
        else:
            return render_template('main/join.html', form=form, organization=org)

    except:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('main.home'))


@main_blueprint.route('/organization/<key>/position/<key2>', methods={'GET', })
@login_required
def position(key, key2):
    org = Organization.query.filter_by(id=key).first()

    if org.owner.id != g.user.id:
        return render_template('errors/403_organization.html'), 403

    pos = Position.query.filter_by(id=key2).first()
    shifts = pos.assigned_shifts.all()
    return render_template('main/position.html', position=pos, organization=org, shifts=shifts)


@main_blueprint.route('/organization/<key>/create_position', methods=['GET', 'POST'])
@login_required
def create_position(key):
    if request.method == 'GET':
        org = Organization.query.filter_by(id=key).first()

        if org.owner.id != g.user.id:
            return render_template('errors/403_organization.html'), 403

        return render_template('main/create_position.html', form=CreateForm())
    else:
        org = Organization.query.filter_by(id=key).first()
        form = PositionForm(request.form)
        if form.validate_on_submit():

            if org.owner.id != g.user.id:
                return render_template('errors/403_organization.html'), 403

            title = form.name.data
            pos = Position(title=title, organization_id=org.id)
            db.session.add(pos)
            org.owned_positions.append(pos)
            db.session.commit()

            return redirect('/organization/' + str(org.id) + '/position/' + str(pos.id))
        else:
            return redirect('/organization/' + str(org.id))
