# project/main/views.py


#################
#### imports ####
#################

from flask import render_template, Blueprint, request, session, g, redirect, url_for, flash
from source import app, db
from flask_login import login_required
from forms import CreateForm, InviteForm

from models import User, Organization
from decorators import check_confirmed


from source.token import generate_confirmation_token, confirm_token, generate_invitation_token, confirm_invitation_token

import datetime
from source.email import send_email
from source.decorators import check_confirmed
################
#    config    #
################

main_blueprint = Blueprint('main', __name__,)


@app.before_request
def load_user():
    if 'user_id' in session:
        if session["user_id"]:
            user = User.query.filter_by(id=session["user_id"]).first()
        else:
            user = {"email": "Guest"}  # Make it better, use an anonymous User instead
    else:
        user = {"email": "Guest"}  # Make it better, use an anonymous User instead

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

    return render_template('main/home.html', organizations=orgs)



@main_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'GET':
        return render_template('main/create.html', form=CreateForm())
    else:
        name = request.form['name']
        owner = g.user

        org = Organization(name=name, owner=owner)

        db.session.add(org)
        db.session.commit()

        return redirect('/organization/' + str(org.id))


@main_blueprint.route('/organization/<key>', methods=['GET', ])
@login_required
def organization(key):
    org = Organization.query.filter_by(id=key).first()

    if org.owner.id != g.user.id:
        return render_template('errors/403_organization.html'), 403

    return render_template('main/organization.html', organization=org)

#
#@main_blueprint.route('/invite', methods=['GET', 'POST'])
#@login_required
#def invite():
#    if request.method == 'GET':
#        return render_template('main/invite.html', form=InviteForm())
#    else:
#        name = request.form['name']
#        owner = g.user
#
#        db.session.add(org)
#        db.session.commit()
#
#        return redirect('/organization/' + str(org.id))
#


@main_blueprint.route('/organization/<key>/invite', methods=['GET', 'POST'])
@login_required
def invite(key):
    # get the organization to invite users to
    org = Organization.query.filter_by(id=key).first()
    form = InviteForm(request.form)
    if form.validate_on_submit():

        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password="temp",
            confirmed=True
            #invited=True
        )
        db.session.add(user)
        #db.session.commit()

        token = generate_invitation_token(user.email)
        #invited_url = url_for('user.confirm_invite_email', token=token, _external=True)
        confirm_url = url_for('user.confirm_email', token=token, _external=True)
        #html = render_template('main/index.html', invited_url=invited_url)
        html = render_template('emails/invitation.html', confirm_url=confirm_url, user=user, organization=org)
        subject = "You've been invited to use SKEDD"
        send_email(user.email, subject, html)

        flash('You succesfully invited' + user.first_name + ' ' + user.last_name + '.', 'success')

        #return redirect(url_for('user.unconfirmed'))

    return render_template('main/invite.html', form=form, organization=org)